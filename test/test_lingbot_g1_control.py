"""Check G1 policy commands with a fake SDK; no robot or model is initialized."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from conf.robots_conf import get_agibot_g1_config


@pytest.fixture
def control_case(monkeypatch):
    sdk_package = ModuleType('a2d_sdk')
    sdk_package.__path__ = []
    sdk_module = ModuleType('a2d_sdk.robot')
    sdk_module.RobotDds = sdk_module.CosineCamera = object
    monkeypatch.setitem(sys.modules, 'a2d_sdk', sdk_package)
    monkeypatch.setitem(sys.modules, 'a2d_sdk.robot', sdk_module)
    path = Path(__file__).resolve().parents[1] / 'client/robots/agibot_g1/body_robot.py'
    spec = importlib.util.spec_from_file_location('client.robots.agibot_g1._test_control', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    now = 10_000_000_000
    monkeypatch.setattr(module, 'time', SimpleNamespace(time_ns=lambda: now, sleep=lambda _: None))

    class SDK:
        def __init__(self):
            self.arm = np.linspace(-0.7, 0.6, 14)
            self.gripper = [36.0, 120.0]
            self.arm_stamp = self.gripper_stamp = self.status_stamp = now
            self.status = {'left_arm_control': True, 'right_arm_control': True}
            self.commands = []
            self.gripper_reads = 0

        def arm_joint_states(self):
            return self.arm, self.arm_stamp

        def gripper_states(self):
            self.gripper_reads += 1
            return self.gripper, self.gripper_stamp

        def whole_body_status(self):
            return self.status, self.status_stamp

        def move_arm(self, positions):
            self.commands.append(('arm', positions.copy()))
            positions[0] = 999  # Native methods must not receive views into model arrays.

        def move_gripper(self, positions):
            self.commands.append(('gripper', positions.copy()))
            positions[0] = 999

        def shutdown(self):
            pass

    sdk = SDK()
    for name in ('arm', 'gripper', 'head', 'waist'):
        setattr(sdk, f'{name}_joint_states_nearest', lambda stamp: ([], stamp))
    monkeypatch.setattr(module, 'Robot', lambda: sdk)
    monkeypatch.setattr(module, 'Camera', lambda names: SimpleNamespace(close=lambda: None))
    cfg = get_agibot_g1_config()
    cfg.gripper_freq = 1
    robot = module.RobotBody(cfg)
    yield SimpleNamespace(robot=robot, sdk=sdk, now=now)
    robot.close()


def target(left=0.9, right=0.3):
    return np.concatenate([np.linspace(-0.6, 0.7, 14), [left, right]])


def test_preparation_samples_without_commands(control_case):
    case = control_case
    case.robot.prepare_policy_control()
    assert case.sdk.commands == []
    assert case.sdk.gripper_reads == 1
    assert case.robot._left_gripper_hold == pytest.approx(0.3)


def test_unprepared_control_cannot_publish(control_case):
    with pytest.raises(RuntimeError, match='prepare_policy_control'):
        control_case.robot.control_robot(target())
    assert control_case.sdk.commands == []


def test_absolute_arms_left_hold_right_curve_and_input_ownership(control_case):
    case = control_case
    case.robot.prepare_policy_control()
    for left_prediction in (0.0, 1.0, -5.0):
        action = target(left=left_prediction)
        saved = action.copy()
        case.robot.control_robot(action)
        assert [kind for kind, _ in case.sdk.commands[-2:]] == ['arm', 'gripper']
        np.testing.assert_array_equal(case.sdk.commands[-2][1], saved[:14])
        np.testing.assert_allclose(case.sdk.commands[-1][1], [0.3, 81 / 2482])
        np.testing.assert_array_equal(action, saved)
    assert case.sdk.gripper_reads == 1


@pytest.mark.parametrize('prediction,expected', [(-0.1, 0), (0, 0), (0.5, 0.5), (1, 1), (1.1, 1)])
def test_right_gripper_clips_before_curve(control_case, prediction, expected):
    case = control_case
    case.robot.prepare_policy_control()
    case.robot.control_robot(target(right=prediction))
    assert case.sdk.commands[-1][1] == pytest.approx([0.3, expected])


def test_hold_changes_only_when_prepared_again(control_case):
    case = control_case
    case.robot.prepare_policy_control()
    case.sdk.gripper[0] = 84.0
    case.robot.control_robot(target())
    assert case.sdk.commands[-1][1][0] == pytest.approx(0.3)
    case.robot.prepare_policy_control()
    case.robot.control_robot(target())
    assert case.sdk.commands[-1][1][0] == pytest.approx(0.7)
    assert case.sdk.gripper_reads == 2


def test_existing_gripper_send_interval_and_prepare_reset(control_case):
    case = control_case
    case.robot.config.gripper_freq = 3
    case.robot.prepare_policy_control()
    for _ in range(5):
        case.robot.control_robot(target())
    assert [kind for kind, _ in case.sdk.commands] == [
        'arm', 'gripper', 'arm', 'arm', 'arm', 'gripper', 'arm',
    ]
    case.robot.prepare_policy_control()
    case.robot.control_robot(target())
    assert case.sdk.commands[-1][0] == 'gripper'


@pytest.mark.parametrize('key,value', [
    ('left_arm_error', 1), ('right_arm_error', 1), ('left_end_error', 1),
    ('right_end_error', 1), ('waist_error', 1), ('lift_error', 1),
    ('left_arm_estop', True), ('right_arm_estop', True),
    ('left_arm_control', False), ('right_arm_control', False),
])
def test_live_fault_blocks_all_commands(control_case, key, value):
    case = control_case
    case.robot.prepare_policy_control()
    case.sdk.status[key] = value
    with pytest.raises(RuntimeError, match=key):
        case.robot.control_robot(target())
    assert case.sdk.commands == []


@pytest.mark.parametrize('field', ['arm_stamp', 'status_stamp'])
@pytest.mark.parametrize('offset', [None, -600_000_000, 600_000_000])
def test_missing_stale_or_future_state_blocks_all_commands(control_case, field, offset):
    case = control_case
    case.robot.prepare_policy_control()
    setattr(case.sdk, field, None if offset is None else case.now + offset)
    with pytest.raises(RuntimeError, match='timestamp|stale'):
        case.robot.control_robot(target())
    assert case.sdk.commands == []


@pytest.mark.parametrize('arm', [np.zeros(13), np.full(14, np.nan)])
def test_invalid_arm_feedback_blocks_commands(control_case, arm):
    case = control_case
    case.robot.prepare_policy_control()
    case.sdk.arm = arm
    with pytest.raises(RuntimeError, match='14 finite'):
        case.robot.control_robot(target())
    assert case.sdk.commands == []


@pytest.mark.parametrize('failure', ['stale', 'shape', 'nan', 'fault'])
def test_failed_preparation_clears_old_hold(control_case, failure):
    case = control_case
    case.robot.prepare_policy_control()
    if failure == 'stale':
        case.sdk.gripper_stamp -= 600_000_000
    elif failure == 'shape':
        case.sdk.gripper = [36.0]
    elif failure == 'nan':
        case.sdk.gripper = [np.nan, 120]
    else:
        case.sdk.status['left_arm_error'] = 1
    with pytest.raises(RuntimeError):
        case.robot.prepare_policy_control()
    assert case.robot._left_gripper_hold is None
    with pytest.raises(RuntimeError, match='prepare_policy_control'):
        case.robot.control_robot(target())
    assert case.sdk.commands == []


@pytest.mark.parametrize('action', [np.zeros(15), np.zeros(20), np.full(16, np.nan)])
def test_invalid_policy_action_does_not_publish_manual_joints(control_case, action):
    case = control_case
    case.robot.prepare_policy_control()
    with pytest.raises(ValueError, match='16 finite'):
        case.robot.control_robot(action)
    assert case.sdk.commands == []


def test_manual_gripper_call_is_not_overridden(control_case):
    case = control_case
    case.robot.execute_action({'gripper': [0.2, 0.4]})
    assert case.sdk.commands == [('gripper', [0.2, 0.4])]


@pytest.fixture
def policy_client(control_case):
    import logging
    import threading
    from unittest.mock import Mock
    from client.core.vla_client import VLAClient

    client = VLAClient.__new__(VLAClient)
    client.robot = control_case.robot
    client.logger = logging.getLogger(__name__)
    client._control_execution_lock = threading.Lock()
    client.is_running = False
    client.is_control_thread_running = False
    client.is_observe_thread_running = False
    client.is_inference_thread_running = False
    client.control_thread_timer = Mock()
    client.control_thread_timer.is_alive.return_value = False
    client.observe_thread = Mock()
    client.process_observe_thread = Mock()
    client.inference_thread = Mock()
    client.task_language_manager = Mock()
    client.realtime_data_manager = Mock()
    client.start_visualize = Mock()
    client.stop_visualize = Mock()
    return client


def test_start_prepares_before_resuming_controls(policy_client, control_case, monkeypatch):
    from unittest.mock import Mock

    def check_prepared():
        assert control_case.robot._left_gripper_hold == pytest.approx(0.3)
        assert not policy_client.is_control_thread_running
        assert control_case.sdk.commands == []

    resume = Mock(side_effect=check_prepared)
    monkeypatch.setattr(control_case.robot, 'resume_controls', resume, raising=False)
    policy_client.start_control()
    resume.assert_called_once()
    assert policy_client.is_control_thread_running
    policy_client.control_thread_timer.start.assert_called_once()
    policy_client.task_language_manager.new_task.assert_called_once()
    control_case.robot.control_robot(target())
    assert control_case.sdk.commands[-1][1][0] == pytest.approx(0.3)


def test_repeated_start_keeps_hold_and_task(policy_client, control_case):
    policy_client.start_control()
    control_case.sdk.gripper[0] = 84.0
    policy_client.start_control()
    assert control_case.sdk.gripper_reads == 1
    assert control_case.robot._left_gripper_hold == pytest.approx(0.3)
    policy_client.task_language_manager.new_task.assert_called_once()
    policy_client.control_thread_timer.start.assert_called_once()


def test_pause_resume_resamples_hold(policy_client, control_case):
    policy_client.start()
    control_case.robot.control_robot(target())
    assert control_case.sdk.commands[-1][1][0] == pytest.approx(0.3)
    policy_client.pause()
    assert not policy_client.is_control_thread_running
    control_case.sdk.gripper[0] = 84.0
    policy_client.resume()
    assert policy_client.is_control_thread_running
    control_case.robot.control_robot(target())
    assert control_case.sdk.commands[-1][1][0] == pytest.approx(0.7)
    assert control_case.sdk.gripper_reads == 2


def test_prepare_failure_keeps_control_disabled_and_allows_retry(policy_client, control_case, monkeypatch):
    from unittest.mock import Mock

    resume = Mock()
    monkeypatch.setattr(control_case.robot, 'resume_controls', resume, raising=False)
    control_case.sdk.gripper_stamp = control_case.now - 1_000_000_000
    with pytest.raises(RuntimeError, match='stale'):
        policy_client.start_control()
    assert not policy_client.is_control_thread_running
    assert control_case.robot._left_gripper_hold is None
    assert control_case.sdk.commands == []
    resume.assert_not_called()
    policy_client.control_thread_timer.start.assert_not_called()
    policy_client.task_language_manager.new_task.assert_not_called()
    control_case.sdk.gripper_stamp = control_case.now
    policy_client.start_control()
    assert policy_client.is_control_thread_running
    resume.assert_called_once()


def test_observe_and_inference_do_not_prepare_or_move(policy_client, control_case):
    policy_client.start_observe()
    policy_client.start_inference()
    assert not policy_client.is_control_thread_running
    assert control_case.sdk.gripper_reads == 0
    assert control_case.sdk.commands == []
    assert control_case.robot._left_gripper_hold is None


def test_robot_without_prepare_uses_existing_resume_path(policy_client):
    from unittest.mock import Mock

    resume = Mock()
    policy_client.robot = SimpleNamespace(resume_controls=resume)
    policy_client.start_control()
    resume.assert_called_once()
    assert policy_client.is_control_thread_running
    policy_client.control_thread_timer.start.assert_called_once()
