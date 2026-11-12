"""Offline adapter tests; no robot SDK or model weights required by default.

Real inference (one saved G1 observation, no robot connection)::

    QWEN25_PATH=/path/to/tokenizer \
    LINGBOT_TEST_REPO_PATH=/path/to/lingbot-vla \
    LINGBOT_TEST_MODEL_PATH=/path/to/hf_ckpt \
    LINGBOT_TEST_NORM_PATH=/path/to/norm_stats.json \
    LINGBOT_TEST_CHUNK_SIZE=25 \
    LINGBOT_TEST_OBSERVATION_DIR=/path/to/g1/runtime_rollouts/episode \
    /path/to/model/python -m pytest -q -s test/test_lingbot_vla_adapter.py

The observation directory must contain G1RolloutRecorder's episode.json,
inference_observations.jsonl and referenced JPEG files. Uses the first row.
"""

import copy
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
import yaml

from server.models.lingbot_vla import ModelVLA


@pytest.fixture(params=[25, 50])
def policy_case(request, tmp_path, monkeypatch):
    horizon = request.param
    repo = tmp_path / 'lingbot-vla'
    (repo / 'deploy').mkdir(parents=True)
    checkpoint = tmp_path / 'hf_ckpt'
    checkpoint.mkdir()
    (checkpoint / 'lingbotvla_cli.yaml').write_text(yaml.safe_dump({
        'train': {'chunk_size': horizon}, 'data': {'data_name': 'package_a2d'},
    }))
    # Both saved JSONs say 50, including the known stale chunk25 JSON.
    (checkpoint / 'config.json').write_text(json.dumps({'chunk_size': 50}))
    norm_path = tmp_path / 'norm_stats.json'
    norm_path.write_text(json.dumps({'norm_stats': {
        'action.arm.position': {
            key: np.zeros((horizon, 14)).tolist()
            for key in ('mean', 'std', 'min', 'max', 'q01', 'q99')
        },
        'action.effector.position': {'mean': [0, 0]},
    }}))
    calls = []
    actions = np.arange(horizon * 16, dtype=np.float32).reshape(horizon, 16) / 100
    case = SimpleNamespace(
        cfg=dict(repo_path=str(repo), model_path=str(checkpoint), norm_path=str(norm_path),
                 chunk_size=horizon, num_denoising_step=7),
        calls=calls, actions=actions, effective_horizon=horizon,
    )

    class FakePolicy:
        def __init__(self, **kwargs):
            calls.append(('load', kwargs))
            self.config = SimpleNamespace(chunk_size=case.effective_horizon)
            self.vla = SimpleNamespace(feature_transform=None)

        def reset(self, task):
            calls.append(('reset', task))
            self.vla.feature_transform = SimpleNamespace(chunk_size=case.effective_horizon)

        def infer(self, observation):
            calls.append(('infer', copy.deepcopy(observation)))
            # LingBot preprocessing mutates its inputs. Detect shared array buffers.
            for value in observation.values():
                if isinstance(value, np.ndarray):
                    value[...] = 0
            observation['new_key'] = 1
            return {'action': case.actions}

    package = ModuleType('deploy')
    package.__path__ = [str(repo / 'deploy')]
    monkeypatch.setitem(sys.modules, 'deploy', package)
    # Only the expected class is available, so selecting the other loader fails.
    module_name, class_name = (
        ('deploy.lingbot_vla_policy_chunk25', 'LingbotVlaChunk25Server') if horizon == 25
        else ('deploy.lingbot_vla_policy', 'LingbotVLAServer')
    )
    module = ModuleType(module_name)
    module.__file__ = str(repo.joinpath(*module_name.split('.')).with_suffix('.py'))
    Path(module.__file__).touch()
    setattr(module, class_name, FakePolicy)
    monkeypatch.setitem(sys.modules, module_name, module)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    return case


def observation():
    state = np.arange(20, dtype=np.float32)
    state[14:16] = [60, 120]  # Raw gripper feedback must not be divided by 120.
    return [{'obs': {
        'state': state,
        'cam.head': np.full((3, 4, 3), [255, 0, 0], dtype=np.uint8),
        'cam.hand_left': np.full((3, 4, 3), [0, 255, 0], dtype=np.uint8),
        'cam.hand_right': np.full((3, 4, 3), [0, 0, 255], dtype=np.uint8),
        'language': ['Pick a soft package from the box.'],
    }, 'ref_timestamp': 123.4, 'loc_timestamp': 567.8}]


def test_mapping_actions_and_input_ownership(policy_case):
    case = policy_case
    model = ModelVLA(case.cfg)
    sequence = observation()
    original = copy.deepcopy(sequence)
    for _ in range(2):
        result = model.infer(sequence)
        np.testing.assert_array_equal(result['pred_action'], case.actions)
        assert not np.shares_memory(result['pred_action'], case.actions)
        assert result['type'] == 'vla_action' and result['ext'] == {}
        assert result['ref_timestamp'] == 123.4 and result['loc_timestamp'] == 567.8
    assert model.cfg is case.cfg
    assert [c[0] for c in case.calls] == ['load', 'reset', 'infer', 'infer']
    assert case.calls[0][1] == dict(
        path_to_pi_model=case.cfg['model_path'], robot_norm_path=case.cfg['norm_path'],
        use_length=case.cfg['chunk_size'], num_denoising_step=7,
        use_compile=False, rtc_mode='off',
    )
    assert case.calls[1][1] == 'package_a2d'
    mapped = case.calls[2][1]
    np.testing.assert_array_equal(mapped['observation.state'], original[0]['obs']['state'][:16])
    assert mapped['task'] == original[0]['obs']['language'][0]
    for target, source in (
        ('observation.images.cam_high_rgb', 'cam.head'),
        ('observation.images.cam_left_wrist_rgb', 'cam.hand_left'),
        ('observation.images.cam_right_wrist_rgb', 'cam.hand_right'),
    ):
        np.testing.assert_array_equal(mapped[target], original[0]['obs'][source])
    assert sequence[0]['obs'].keys() == original[0]['obs'].keys()
    for key, value in original[0]['obs'].items():
        np.testing.assert_array_equal(sequence[0]['obs'][key], value)


def test_native_16_dimensional_state(policy_case):
    model = ModelVLA(policy_case.cfg)
    sequence = observation()
    sequence[0]['obs']['state'] = sequence[0]['obs']['state'][:16]
    model.infer(sequence)
    np.testing.assert_array_equal(policy_case.calls[-1][1]['observation.state'][14:], [60, 120])


def test_wrong_training_horizon_rejected_before_loading(policy_case):
    policy_case.cfg['chunk_size'] = 75 - policy_case.cfg['chunk_size']
    with pytest.raises(ValueError, match='train.chunk_size'):
        ModelVLA(policy_case.cfg)
    assert not policy_case.calls


def test_wrong_stats_rejected_before_loading(policy_case):
    path = Path(policy_case.cfg['norm_path'])
    stats = json.loads(path.read_text())
    stats['norm_stats']['action.arm.position']['q99'] = [[0] * 14]
    path.write_text(json.dumps(stats))
    with pytest.raises(ValueError, match='normalization q99'):
        ModelVLA(policy_case.cfg)
    assert not policy_case.calls


def test_effective_horizon_checked_after_reset(policy_case):
    policy_case.effective_horizon = 75 - policy_case.cfg['chunk_size']
    with pytest.raises(ValueError, match='wrong chunk_size'):
        ModelVLA(policy_case.cfg)
    assert [c[0] for c in policy_case.calls] == ['load', 'reset']


@pytest.mark.parametrize('bad_output', ['transposed', 'short', 'nan'])
def test_invalid_output_rejected(policy_case, bad_output):
    model = ModelVLA(policy_case.cfg)
    if bad_output == 'transposed':
        policy_case.actions = policy_case.actions.T
    elif bad_output == 'short':
        policy_case.actions = policy_case.actions[:1]
    else:
        policy_case.actions[0, 0] = np.nan
    with pytest.raises(ValueError, match='actions must be finite'):
        model.infer(observation())


@pytest.mark.parametrize('bad_input', ['history', 'state', 'nan', 'image', 'language'])
def test_invalid_input_rejected(policy_case, bad_input):
    model = ModelVLA(policy_case.cfg)
    sequence = observation()
    if bad_input == 'history':
        sequence *= 2
    elif bad_input == 'state':
        sequence[0]['obs']['state'] = np.zeros(15)
    elif bad_input == 'nan':
        sequence[0]['obs']['state'][0] = np.nan
    elif bad_input == 'image':
        sequence[0]['obs']['cam.head'] = np.zeros((3, 4, 3), dtype=np.float32)
    else:
        sequence[0]['obs']['language'] = 'Not a list'
    with pytest.raises(ValueError):
        model.infer(sequence)
    assert [c[0] for c in policy_case.calls] == ['load', 'reset']


def test_real_saved_observation():
    model_path = os.environ.get('LINGBOT_TEST_MODEL_PATH')
    if not model_path:
        pytest.skip('Set LINGBOT_TEST_* paths to run real GPU inference')
    import cv2
    import torch

    cfg = dict(
        repo_path=os.environ['LINGBOT_TEST_REPO_PATH'], model_path=model_path,
        norm_path=os.environ['LINGBOT_TEST_NORM_PATH'],
        chunk_size=int(os.environ['LINGBOT_TEST_CHUNK_SIZE']),
        num_denoising_step=int(os.environ.get('LINGBOT_TEST_DENOISING_STEPS', '10')),
    )
    episode_dir = Path(os.environ['LINGBOT_TEST_OBSERVATION_DIR'])
    metadata = json.loads((episode_dir / 'episode.json').read_text())
    assert metadata['schema_version'] == 'g1.rollout.raw.v2'
    with (episode_dir / 'inference_observations.jsonl').open() as f:
        row = json.loads(next(f))
    obs = {'state': np.asarray(row['state'], dtype=np.float32),
           'language': [metadata['task_instruction']]}
    for camera in ('head', 'hand_left', 'hand_right'):
        # G's recorder feeds RGB arrays directly to cv2.imencode. cv2.imread
        # reconstructs those same channel positions; do NOT swap them again.
        obs[f'cam.{camera}'] = cv2.imread(str(episode_dir / row['camera_paths'][camera]))
        assert obs[f'cam.{camera}'] is not None
    data = {'obs': obs, 'ref_timestamp': row['capture_monotonic_ns'] / 1e9,
            'loc_timestamp': row['capture_wall_time_ns'] / 1e9}
    original = copy.deepcopy(data)
    torch.cuda.synchronize()
    started = time.perf_counter()
    model = ModelVLA(cfg)
    torch.cuda.synchronize()
    load_s = time.perf_counter() - started
    started = time.perf_counter()
    result = model.infer([data])
    torch.cuda.synchronize()
    infer_s = time.perf_counter() - started
    assert result['pred_action'].shape == (cfg['chunk_size'], 16)
    assert np.isfinite(result['pred_action']).all()
    assert result['ref_timestamp'] == data['ref_timestamp']
    assert result['loc_timestamp'] == data['loc_timestamp']
    for key in obs:
        np.testing.assert_array_equal(obs[key], original['obs'][key])
    print('\nM03_REAL_RESULT=' + json.dumps({
        **cfg, 'observation_dir': str(episode_dir), 'chunk': row['chunk'],
        'task': obs['language'][0], 'shape': list(result['pred_action'].shape),
        'load_seconds': load_s, 'first_infer_seconds': infer_s,
    }, ensure_ascii=False))
