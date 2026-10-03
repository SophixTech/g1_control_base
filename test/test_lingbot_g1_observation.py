"""G1 observation contract tests using fake SDK objects, without robot/GPU access."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import pytest

from conf.robots_conf import get_agibot_g1_config
from client.core.vla_client import VLAClient
from server.core.vla_server import VLAServer
from server.models.lingbot_vla import ModelVLA


COLORS = {'head': (240, 20, 40), 'hand_left': (30, 230, 50), 'hand_right': (20, 40, 240)}


def packet(camera, encoding, color_format, timestamp):
    rgb = np.full((32, 40, 3), COLORS[camera], dtype=np.uint8)
    if encoding in ('JPEG', 'PNG'):
        ok, data = cv2.imencode('.jpg' if encoding == 'JPEG' else '.png', rgb[:, :, ::-1])
        assert ok
    else:
        data = (rgb if color_format == 'RGB' else rgb[:, :, ::-1]).copy().ravel()
    return SimpleNamespace(
        send_timestamp=timestamp, encoding_format=f'EncodingFormat.{encoding}',
        color_format=f'ColorFormat.{color_format}', image_height=32, image_width=40,
        get_image_data=lambda: data,
    )


@pytest.fixture
def body_module(monkeypatch):
    # Do not import the native SDK, whose module initialization can create logs/threads.
    sdk = ModuleType('a2d_sdk')
    sdk.__path__ = []
    sdk_robot = ModuleType('a2d_sdk.robot')
    sdk_robot.RobotDds = sdk_robot.CosineCamera = object
    monkeypatch.setitem(sys.modules, 'a2d_sdk', sdk)
    monkeypatch.setitem(sys.modules, 'a2d_sdk.robot', sdk_robot)
    path = Path(__file__).resolve().parents[1] / 'client/robots/agibot_g1/body_robot.py'
    spec = importlib.util.spec_from_file_location('client.robots.agibot_g1._test_body', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'time', SimpleNamespace(sleep=lambda _: None))
    return module


@pytest.fixture
def robot_case(body_module, monkeypatch):
    frames = {name: packet(name, 'JPEG', 'RGB', 1000 + index)
              for index, name in enumerate(COLORS)}
    camera_calls = []
    joint_calls = []
    joints = {
        'arm': np.linspace(-0.7, 0.6, 14, dtype=np.float32),
        'gripper': np.array([60, 120], dtype=np.float32),
        'head': np.array([0.1, 0.2], dtype=np.float32),
        'waist': np.array([0.3, 0.4], dtype=np.float32),
    }

    class Camera:
        def __init__(self, names):
            assert set(names) == set(COLORS)

        def get_latest_packet(self, name):
            assert name == 'head'  # Wrist metadata must come from the selected nearest packet.
            camera_calls.append(('latest', name))
            return frames[name]

        def get_packet_nearest(self, name, stamp):
            camera_calls.append(('nearest', name, stamp))
            return frames[name]

        def close(self):
            pass

    def read_joint(name, timestamp):
        joint_calls.append((name, timestamp))
        return joints[name], timestamp - 1

    sdk_robot = SimpleNamespace(shutdown=lambda: None, **{
        f'{name}_joint_states_nearest': lambda timestamp, name=name: read_joint(name, timestamp)
        for name in joints
    })
    monkeypatch.setattr(body_module, 'Robot', lambda: sdk_robot)
    monkeypatch.setattr(body_module, 'Camera', Camera)
    robot = body_module.RobotBody(get_agibot_g1_config())
    yield SimpleNamespace(robot=robot, frames=frames, joints=joints,
                          camera_calls=camera_calls, joint_calls=joint_calls)
    robot.close()


@pytest.mark.parametrize('encoding,color_format', [
    ('JPEG', 'RGB'), ('PNG', 'BGR'), ('RAW', 'RGB'), ('RAW', 'BGR'),
])
def test_packet_to_bgr(body_module, encoding, color_format):
    frame = packet('head', encoding, color_format, 1)
    image = body_module.RobotBody._packet_to_bgr(frame)
    assert image.dtype == np.uint8 and image.shape == (32, 40, 3)
    np.testing.assert_allclose(image[16, 20], COLORS['head'][::-1], atol=2)


def test_first_state_preserves_all_groups_and_raw_grippers(robot_case):
    case = robot_case
    result = case.robot.retrieve_observation()
    expected = np.concatenate(list(case.joints.values()))
    np.testing.assert_array_equal(result['obs.state'], expected)
    assert result['obs.state'].shape == (20,)
    # Display normalization must not change the model/recorder state.
    np.testing.assert_allclose(case.robot.current_state[14:16], [(60 - 35) / 85, 1])
    np.testing.assert_array_equal(result['obs.state'][14:16], [60, 120])
    assert case.joint_calls == [(name, 1000) for name in ('arm', 'gripper', 'head', 'waist')]
    assert ('latest', 'head') in case.camera_calls
    assert set(call for call in case.camera_calls if call[0] == 'nearest') == {
        ('nearest', 'hand_left', 1000), ('nearest', 'hand_right', 1000),
    }
    case.joints['arm'][:] = 0.5
    case.joints['gripper'][:] = [10, 90]
    case.frames['head'].send_timestamp = 2000
    second = case.robot.retrieve_observation()
    np.testing.assert_array_equal(second['obs.state'], np.concatenate(list(case.joints.values())))
    np.testing.assert_array_equal(result['obs.state'], expected)


def test_mixed_packets_reach_model_as_rgb_and_raw_state(robot_case):
    case = robot_case
    case.frames['hand_left'] = packet('hand_left', 'RAW', 'RGB', 995)
    case.frames['hand_right'] = packet('hand_right', 'RAW', 'BGR', 1005)
    frame = case.robot.retrieve_observation()
    client = VLAClient.__new__(VLAClient)
    client._preprocess_func = None  # The package task disables additional resizing in M08.
    client.image_process_time = 0
    client.task_language_manager = SimpleNamespace(get_current_language=lambda: 'Move the package.')
    with ThreadPoolExecutor(max_workers=3) as pool:
        client._img_executor = pool
        data, _ = client._process_data(frame)
    server = VLAServer.__new__(VLAServer)
    server.config = {'image_pad_and_resize': False}
    for name in COLORS:
        key, rgb = server._image_decode_thread_func(f'cam.{name}', data['obs'][f'cam.{name}'])
        data['obs'][key] = rgb

    received = []
    adapter = ModelVLA.__new__(ModelVLA)
    adapter.chunk_size = 25
    def infer(observation):
        received.append(observation)
        return {'action': np.zeros((25, 16), dtype=np.float32)}
    adapter.policy = SimpleNamespace(infer=infer)
    output = adapter.infer([data])
    model_obs = received[0]
    for name, key in [('head', 'cam_high_rgb'), ('hand_left', 'cam_left_wrist_rgb'),
                      ('hand_right', 'cam_right_wrist_rgb')]:
        np.testing.assert_allclose(model_obs[f'observation.images.{key}'][16, 20],
                                   COLORS[name], atol=4)  # Existing JPEG transport is lossy.
    np.testing.assert_array_equal(model_obs['observation.state'], frame['obs.state'][:16])
    np.testing.assert_array_equal(model_obs['observation.state'][14:16], [60, 120])
    assert model_obs['task'] == 'Move the package.'
    assert output['ref_timestamp'] == 1000
    assert output['loc_timestamp'] == data['loc_timestamp']


def test_duplicate_reference_does_not_resample(robot_case):
    case = robot_case
    assert case.robot.retrieve_observation() is not None
    previous_joints = list(case.joint_calls)
    previous_nearest = [c for c in case.camera_calls if c[0] == 'nearest']
    assert case.robot.retrieve_observation() is None
    assert case.joint_calls == previous_joints
    assert [c for c in case.camera_calls if c[0] == 'nearest'] == previous_nearest


def test_missing_wrist_does_not_consume_reference_timestamp(robot_case):
    case = robot_case
    wrist = case.frames['hand_left']
    case.frames['hand_left'] = None
    assert case.robot.retrieve_observation() is None
    assert case.robot.current_timestamp == 0
    case.frames['hand_left'] = wrist
    assert case.robot.retrieve_observation()['ref_timestamp'] == 1000


def test_unsupported_raw_color_is_not_used_as_rgb(robot_case):
    robot_case.frames['hand_right'].encoding_format = 'EncodingFormat.RAW'
    robot_case.frames['hand_right'].color_format = 'ColorFormat.RS2_FORMAT_Z16'
    assert robot_case.robot.retrieve_observation() is None
