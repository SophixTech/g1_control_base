"""Offline ECOT contract/isolation tests: no GPU, weights or robot connection."""

import copy
import json
import os
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import yaml

from server.models.lingbot_ecot import ModelVLA


@pytest.fixture
def case(tmp_path, monkeypatch):
    repo = tmp_path / 'ecot'
    checkpoint = tmp_path / 'checkpoint'
    checkpoint.mkdir()
    config = dict(repo_path=str(repo), model_path=str(checkpoint), norm_path=str(tmp_path / 'stats.json'),
                  chunk_size=50, num_denoising_step=10)
    training = {'train': {'chunk_size': 50, 'ecot_aux_supervision': True, 'use_lora': True},
                'data': {'data_name': 'package_a2d', 'robot_config_root': 'configs/robot_configs'}}
    (checkpoint / 'lingbotvla_cli.yaml').write_text(yaml.safe_dump(training))
    (checkpoint / 'config.json').write_text(json.dumps({'chunk_size': 50, 'n_action_steps': 50}))
    robot_file = repo / 'configs/robot_configs/package_a2d.yaml'
    robot_file.parent.mkdir(parents=True)
    robot_file.write_text(yaml.safe_dump({'actions': [
        {'action.arm.position': {'subtract_state': True}},
        {'action.effector.position': {'subtract_state': False}},
    ]}))
    stats = {}
    for feature, shape in [('action.arm.position', (50, 14)), ('action.effector.position', (2,)),
                           ('observation.state.arm.position', (14,)), ('observation.state.effector.position', (2,))]:
        stats[feature] = {key: np.zeros(shape).tolist() for key in ('mean', 'std', 'min', 'max', 'q01', 'q99')}
    Path(config['norm_path']).write_text(json.dumps({'norm_stats': stats}))
    header = {}
    for head, size in [('subtask', 4), ('bbox', 4), ('label', 2)]:
        for layer in ('0.weight', '0.bias', '1.weight', '1.bias'):
            header[f'model.ecot_{head}_head.{layer}'] = {'shape': [size, 8], 'dtype': 'F32', 'data_offsets': [0, 0]}
    for name in ('lora_A', 'lora_B'):
        header[f'model.{name}.weight'] = {'shape': [8, 8], 'dtype': 'F32', 'data_offsets': [0, 0]}
    weights = checkpoint / 'model.safetensors'
    def save_header():
        content = json.dumps(header).encode()
        weights.write_bytes(struct.pack('<Q', len(content)) + content)
    save_header()
    for name in (ModelVLA.MODULE, ModelVLA.MODEL_MODULE):
        file = repo.joinpath(*name.split('.')).with_suffix('.py')
        file.parent.mkdir(parents=True, exist_ok=True)
        file.touch()
        module = ModuleType(name)
        module.__file__ = str(file)
        monkeypatch.setitem(sys.modules, name, module)
    calls = []
    actions = np.linspace(-.3, .3, 800, dtype=np.float32).reshape(50, 16)
    result = SimpleNamespace(config=config, calls=calls, actions=actions, header=header,
                             save_header=save_header, training=training, checkpoint=checkpoint)
    class Policy:
        def __init__(self, **kwargs):
            calls.append(('load', kwargs))
            self.config = SimpleNamespace(chunk_size=50)
            self.vla = SimpleNamespace(feature_transform=SimpleNamespace(chunk_size=50),
                                      model=SimpleNamespace(ecot_aux_supervision=True,
                                                            ecot_subtask_head=object(), ecot_bbox_head=object(),
                                                            ecot_label_head=object()))
        def reset(self, task):
            calls.append(('reset', task))
        def infer(self, observation):
            calls.append(('infer', copy.deepcopy(observation)))
            for value in observation.values():
                if isinstance(value, np.ndarray):
                    value[:] = 0
            return {'action': result.actions}
    sys.modules[ModelVLA.MODULE].LingbotVLAServer = Policy
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    return result


def observation():
    return [{'obs': {'state': np.arange(20, dtype=np.float32), 'language': ['conditional task'],
                     **{key: np.full((4, 5, 3), j + 1, dtype=np.uint8)
                        for j, key in enumerate(ModelVLA.CAMERA_KEYS)}},
             'ref_timestamp': 123, 'loc_timestamp': 456.0}]


def test_action_contract_and_input_ownership(case):
    model = ModelVLA(case.config)
    source = observation()
    before = copy.deepcopy(source)
    output = model.infer(source)
    assert output['ref_timestamp'] == 123 and output['loc_timestamp'] == 456.0
    np.testing.assert_array_equal(output['pred_action'], case.actions)
    assert not np.shares_memory(output['pred_action'], case.actions)
    assert output['ext'] == {} and output['type'] == 'vla_action'
    for key, value in before[0]['obs'].items():
        np.testing.assert_array_equal(source[0]['obs'][key], value)
    mapped = case.calls[-1][1]
    np.testing.assert_array_equal(mapped['observation.state'], before[0]['obs']['state'][:16])
    for source_key, target in ModelVLA.CAMERA_KEYS.items():
        np.testing.assert_array_equal(mapped[target], before[0]['obs'][source_key])
    assert case.calls[0][1]['rtc_mode'] == 'off'
    assert case.calls[0][1]['use_length'] == 50
    assert case.calls[1] == ('reset', 'package_a2d')


@pytest.mark.parametrize('bad', [np.zeros((25, 16)), np.full((50, 16), np.nan)])
def test_bad_model_outputs_rejected(case, bad):
    model = ModelVLA(case.config)
    case.actions = bad
    with pytest.raises(ValueError, match='ECOT actions'):
        model.infer(observation())


def test_legacy_checkpoint_rejected_before_loading(case):
    case.training['train']['ecot_aux_supervision'] = False
    (case.checkpoint / 'lingbotvla_cli.yaml').write_text(yaml.safe_dump(case.training))
    with pytest.raises(ValueError, match='ecot_aux_supervision'):
        ModelVLA(case.config)
    assert not case.calls


def test_missing_head_rejected_before_loading(case):
    del case.header['model.ecot_label_head.1.weight']
    case.save_header()
    with pytest.raises(ValueError, match='Missing ECOT weight'):
        ModelVLA(case.config)
    assert not case.calls


def test_bad_normalization_rejected(case):
    file = Path(case.config['norm_path'])
    data = json.loads(file.read_text())
    data['norm_stats']['action.arm.position']['q99'] = np.zeros((25, 14)).tolist()
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='normalization'):
        ModelVLA(case.config)
    assert not case.calls


@pytest.mark.parametrize('module', [ModelVLA.MODULE, ModelVLA.MODEL_MODULE])
def test_foreign_source_module_rejected(case, monkeypatch, module):
    monkeypatch.setattr(sys.modules[module], '__file__', '/legacy/' + module.replace('.', '/') + '.py')
    with pytest.raises(ImportError, match='collision'):
        ModelVLA(case.config)
    assert not case.calls


def test_foreign_package_search_path_rejected(case, monkeypatch):
    package = ModuleType('lingbotvla')
    package.__path__ = ['/legacy/lingbotvla']
    monkeypatch.setitem(sys.modules, 'lingbotvla', package)
    with pytest.raises(ImportError, match='collision'):
        ModelVLA(case.config)


def test_config_and_cli_are_independent(monkeypatch):
    from conf.models_conf import ModelType
    from conf.server_conf import get_vla_server_config
    from run_server import override_config_with_args, parse_args
    config = get_vla_server_config()
    original = config.models.lingbot_vla.to_dict()
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--model_type', 'lingbot_ecot',
                                     '--model_path', '/ecot/weights', '--norm_path', '/ecot/stats.json'])
    override_config_with_args(config, parse_args())
    assert config.models.type == ModelType.LINGBOT_ECOT
    assert config.models.lingbot_vla.to_dict() == original
    assert config.models.lingbot_ecot.model_path == '/ecot/weights'
    assert config.zmq.port == '5566' and config.max_infer_workers == 1
    legacy = get_vla_server_config()
    ecot_defaults = legacy.models.lingbot_ecot.to_dict()
    monkeypatch.setattr(sys, 'argv', ['run_server.py', '--model_type', 'lingbot_vla', '--chunk_size', '25'])
    override_config_with_args(legacy, parse_args())
    assert legacy.models.lingbot_ecot.to_dict() == ecot_defaults
    assert legacy.models.lingbot_vla.chunk_size == 25 and legacy.zmq.port == '5566'


def test_client_profiles_do_not_share_mutable_files():
    root = Path(__file__).resolve().parents[1]
    old = yaml.safe_load((root / 'conf/lingbot_package.yaml').read_text())
    new = yaml.safe_load((root / 'conf/lingbot_ecot_package.yaml').read_text())
    assert new['language']['file_path'] != old['language']['file_path']
    assert new['record']['save_dir'] != old['record']['save_dir']
    assert new['vla_zmq']['port'] == old['vla_zmq']['port'] == '5566'
    assert new['rdm']['mode'] == 'async' and new['intra_chunk']['intra_chunk_mode'] == 'fitting'


def test_real_saved_observation_matches_native():
    """Opt-in GPU check using a saved G1 observation; never accesses a robot."""
    episode_path = os.environ.get('ECOT_TEST_OBSERVATION_DIR')
    if not episode_path:
        pytest.skip('Set ECOT_TEST_* paths to run real GPU inference')
    import cv2
    import torch

    cfg = dict(repo_path=os.environ['ECOT_TEST_REPO_PATH'],
               model_path=os.environ['ECOT_TEST_MODEL_PATH'],
               norm_path=os.environ['ECOT_TEST_NORM_PATH'], chunk_size=50, num_denoising_step=10)
    episode = Path(episode_path)
    metadata = json.loads((episode / 'episode.json').read_text())
    assert metadata['schema_version'] == 'g1.rollout.raw.v2'
    with (episode / 'inference_observations.jsonl').open() as stream:
        row = json.loads(next(stream))
    root = Path(__file__).resolve().parents[1]
    task = json.loads((root / 'conf/lingbot_ecot_package_language.json').read_text())['package_a2d'][0]
    obs = {'state': np.asarray(row['state'], dtype=np.float32), 'language': [task]}
    for camera in ('head', 'hand_left', 'hand_right'):
        # Raw-v2 recorder passes RGB directly to cv2.imencode; preserve channel order.
        obs[f'cam.{camera}'] = cv2.imread(str(episode / row['camera_paths'][camera]))
        assert obs[f'cam.{camera}'] is not None
    source = {'obs': obs, 'ref_timestamp': row['capture_monotonic_ns'] / 1e9,
              'loc_timestamp': row['capture_monotonic_ns'] / 1e9}
    original = copy.deepcopy(source)
    model = ModelVLA(cfg)  # Native loader must strictly load the real ECOT weights.
    torch.manual_seed(42)
    result = model.infer([source])
    direct = {'observation.state': np.array(obs['state'][:16], dtype=np.float32, copy=True),
              'task': task}
    for source_key, target in ModelVLA.CAMERA_KEYS.items():
        direct[target] = obs[source_key].copy()
    model.policy.reset('package_a2d')
    torch.manual_seed(42)
    native = model.policy.infer(direct)['action']
    np.testing.assert_allclose(result['pred_action'], native, atol=1e-5, rtol=1e-5)
    assert result['pred_action'].shape == (50, 16) and np.isfinite(result['pred_action']).all()
    for key in obs:
        np.testing.assert_array_equal(obs[key], original['obs'][key])
    assert result['ref_timestamp'] == source['ref_timestamp']
