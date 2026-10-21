"""Offline V2 contracts; no GPU allocation, weights, or robot connection."""
import ast
import copy
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import yaml

from server.models.lingbot_v2 import ModelVLA


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo = tmp_path / 'v2'
    entry = repo / 'deploy/lingbot_vla_v2_policy.py'
    entry.parent.mkdir(parents=True)
    entry.touch()
    checkpoint = tmp_path / 'run/checkpoints/step_100/hf_ckpt'
    checkpoint.mkdir(parents=True)
    (checkpoint.parent.parent.parent / 'lingbotvla_cli.yaml').write_text(
        yaml.safe_dump({'model': {}, 'train': {'chunk_size': 50}}))
    norm = tmp_path / 'stats.json'
    norm.write_text('{}')
    cfg = dict(repo_path=str(repo), model_path=str(checkpoint), norm_path=str(norm),
               chunk_size=50, num_denoising_step=7)
    calls = []
    module = ModuleType(ModelVLA.MODULE)
    module.__file__ = str(entry)
    class Policy:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.config = SimpleNamespace(chunk_size=50, num_steps=10)
            self.vla = SimpleNamespace(model=SimpleNamespace(config=self.config))
            self.data_config = SimpleNamespace(joints=[{'arm.position': 14}],
                                               norm_type=[{'arm.position': 'meanstd'}])
            self.processor = object()
            self.robot_norm_path = kwargs['robot_norm_path']
            self.chunk_ret = kwargs['chunk_ret']
        def infer(self, observation):
            calls.append(copy.deepcopy(observation))
            # Each call must carry the current observation, without additional delta restoration.
            return {'action': np.tile(observation['observation.state'], (50, 1)) + .25}
    def transform(path, data_config, model_config, processor, **kwargs):
        assert Path(path).is_absolute()
        assert isinstance(data_config.joints[0], str)
        assert isinstance(data_config.norm_type[0], str)
        assert yaml.safe_load(Path(path).read_text())['norm_stats'] is None
        return SimpleNamespace(org_features={'actions': ['action']})
    module.LingbotVLAv2Server = Policy
    module.FeatureTransform = transform
    # isolate from fake modules installed by other adapter tests
    for key in list(sys.modules):
        if key in ('deploy', 'lingbotvla') or key.startswith(('deploy.', 'lingbotvla.')):
            monkeypatch.delitem(sys.modules, key)
    monkeypatch.setitem(sys.modules, ModelVLA.MODULE, module)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    return SimpleNamespace(config=cfg, calls=calls)


def observation(value):
    obs = {'state': np.full(20, value), 'language': ['pick package']}
    obs.update({k: np.zeros((12, 16, 3), dtype=np.uint8) for k in ModelVLA.CAMERA_KEYS})
    return [{'obs': obs, 'ref_timestamp': 10, 'loc_timestamp': 12}]


def test_fresh_chunks_and_absolute_actions(case):
    model = ModelVLA(case.config)
    assert case.calls[0]['chunk_ret'] is True
    assert case.calls[0]['use_length'] == 50
    assert model.policy.config.num_steps == 7
    for state in (.1, .6):
        data = observation(state)
        result = model.infer(data)
        np.testing.assert_allclose(result['pred_action'], state + .25)
        assert result['pred_action'].shape == (50, 16)
        assert result['ref_timestamp'] == 10 and result['loc_timestamp'] == 12
        np.testing.assert_array_equal(data[0]['obs']['state'], state)
    assert len(case.calls) == 3


def test_horizon_mismatch(case):
    case.config['chunk_size'] = 25
    with pytest.raises(ValueError, match='training horizon'):
        ModelVLA(case.config)


def test_vla_server_initialization(case):
    from unittest.mock import Mock
    from conf.server_conf import get_vla_server_config
    from conf.models_conf import ModelType
    from server.core.vla_server import VLAServer

    config = get_vla_server_config()
    config.models.type = ModelType.LINGBOT_V2
    config.max_infer_workers = 1
    model = ModelVLA(case.config)
    transport = Mock()
    server = VLAServer(config, transport, model)
    try:
        transport.set_heartbeat_info.assert_called_once_with(
            model_type=str(ModelType.LINGBOT_V2),
            model_path=case.config['model_path'],
            lang_cmd='No language command received.',
        )
        assert server.model is model
        assert not server.receive_thread.is_alive()
    finally:
        server.executor.shutdown(wait=True)
        server.image_decode_executor.shutdown(wait=True)


def test_bad_output_rejected(case):
    model = ModelVLA(case.config)
    model.policy.infer = lambda obs: {'action': np.zeros((50, 55))}
    with pytest.raises(ValueError, match='shape'):
        model.infer(observation(0))


def test_cli_and_independent_config(monkeypatch):
    import run_server
    from conf.server_conf import get_vla_server_config
    config = get_vla_server_config()
    old = config.models.lingbot_ori.to_dict()
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--model_type', 'lingbot_v2',
                                     '--model_path', '/v2/hf_ckpt', '--norm_path', '/v2/stats.json',
                                     '--num_denoising_step', '6', '--image_profile', 'crop_1016'])
    run_server.override_config_with_args(config, run_server.parse_args())
    assert config.models.lingbot_v2.model_path == '/v2/hf_ckpt'
    assert config.models.lingbot_v2.image_profile == 'crop_1016'
    assert config.models.lingbot_v2.num_denoising_step == 6
    assert config.max_infer_workers == 1
    assert config.models.lingbot_ori.to_dict() == old


def test_native_chunk_ret_recomputes():
    """Execute the actual native infer method without importing CUDA/model dependencies."""
    native = Path(__file__).resolve().parents[2] / 'ORI-lingbot-vlaV2/deploy/lingbot_vla_v2_policy.py'
    if not native.exists():
        pytest.skip('Native V2 checkout is not present')
    tree = ast.parse(native.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LingbotVLAv2Server')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'infer')
    ns = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(native), 'exec'), ns)
    calls = []
    def batch(obs):
        calls.append(obs)
        return {'action': np.full((1, 50, 16), len(calls), dtype=np.float32)}
    policy = SimpleNamespace(chunk_ret=True, use_length=50, global_step=0,
                             last_action_chunk=None, last_normalized_action_chunk=None,
                             _infer_batch=batch)
    for i in (1, 2, 3):
        response = ns['infer'](policy, {'task': str(i)})
        assert response['action'].shape == (50, 16)
        np.testing.assert_array_equal(response['action'], i)
    assert len(calls) == 3


def test_native_joint_mapping():
    """Run native V2 FeatureTransform on CPU in its own environment."""
    import os
    import subprocess
    root = Path(__file__).resolve().parents[1]
    repo = root.parent / 'ORI-lingbot-vlaV2'
    python = repo / '.venv/bin/python'
    if not python.exists():
        pytest.skip('Native V2 environment is not present')
    env = dict(os.environ, PYTHONPATH=str(repo), OPEN_RAIL_TEST_ROOT=str(root))
    subprocess.run([str(python), '-c', NATIVE_MAPPING_CHECK], env=env, check=True, timeout=60)


NATIVE_MAPPING_CHECK = r'''
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
import yaml
from lingbotvla.data.vla_data.utils import FeatureTransform
import os
root=Path(os.environ['OPEN_RAIL_TEST_ROOT'])
training=yaml.safe_load((root.parent/'ORI-lingbot-vlaV2/configs/vla/real_robot/real_robot.yaml').read_text())
data=SimpleNamespace(**training['data'])
for key in ('joints','norm_type'):
    setattr(data,key,[repr(x) for x in getattr(data,key)])
# Synthetic statistics exercise scaling and offsets, independently of model weights.
stats={}
for prefix in ('action','observation.state'):
    for group,n in [('arm.position',14),('effector.position',2)]:
        stats[f'{prefix}.{group}']={'mean':np.full(n,.1).tolist(),'std':np.full(n,.5).tolist()}
with tempfile.TemporaryDirectory() as tmp:
    norm=Path(tmp)/'stats.json';norm.write_text(json.dumps({'norm_stats':stats}))
    transform=FeatureTransform(str(root/'server/models/lingbot_v2/package_a2d.yaml'),data,
        SimpleNamespace(max_state_dim=55,max_action_dim=55),None,
        chunk_size=50,norm_stats_path=str(norm),disabled_image_features=True)
    mask=torch.zeros(55,dtype=torch.bool);mask[:14]=True;mask[28:30]=True
    state=torch.zeros(55);state[:14]=.4;state[28:30]=.8
    actions=torch.full((50,55),999.);actions[:,:14]=.2;actions[:,28:30]=.6
    result=transform.unapply({'state':state,'actions':actions,
                             'state_joint_mask':mask,'action_joint_mask':mask})['action']
    expected=np.zeros((50,16));expected[:,:14]=.5;expected[:,14:]=.4
    np.testing.assert_allclose(result,expected,atol=2e-6)
    print('Native V2 unapply PASS: (50,55) -> (50,16); arms add state once; grippers use slots 28:30 without state addition.')
'''
