"""Exercise G1 command methods offline, without importing the hardware SDK."""
import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import time
from client.core.gripper_delay import GripperDelay


@pytest.fixture
def robot():
    source = Path(__file__).resolve().parents[1] / 'client/robots/agibot_g1/body_robot.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'RobotBody')
    names = {'prepare_policy_control', 'control_robot', 'set_right_gripper_quartic_enabled',
             'get_policy_left_arm_hold_position', 'execute_action'}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {'np': np, 'time': time}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
    commands = []
    body = SimpleNamespace(
        _policy_control_ready=False, gripper_count=0, config={'gripper_freq': 1},
        _left_arm_hold_position=None,
        _gripper_delay=GripperDelay(),
        _joint_trace=None, _check_live_status=lambda: None, _check_fresh=lambda *args: None,
        robot=SimpleNamespace(gripper_states=lambda: ([0.0, 60.0], 1)),
        _send_arm_command=lambda values, *args, **kwargs: commands.append(('arm', values)),
        _send_gripper_command=lambda values, *args, **kwargs: commands.append(('gripper', values)),
    )
    for name in names:
        setattr(body, name, namespace[name].__get__(body))
    return body, commands


def test_left_follows_model_even_when_initial_feedback_is_zero(robot):
    body, commands = robot
    body.prepare_policy_control()
    action = np.arange(16, dtype=float) / 20
    for left in (0.2, 0.8):
        action[14] = left
        body.control_robot(action)
        assert commands[-1][1][0] == left
        assert commands[-2][1] == action[:14].tolist()
        right = action[15]
        assert commands[-1][1][1] == pytest.approx(right**4 / (right**4 + (1-right)**4))


@pytest.mark.parametrize('value,expected', [(-0.2, 0.0), (1.2, 1.0)])
def test_left_command_clipped_to_sdk_range(robot, value, expected):
    body, commands = robot
    body.prepare_policy_control()
    action = np.zeros(16)
    action[14] = value
    body.control_robot(action)
    assert commands[-1] == ('gripper', [expected, 0.0])


def test_preparation_required_and_failed_preparation_revokes_ready(robot):
    body, commands = robot
    with pytest.raises(RuntimeError, match='prepare_policy_control'):
        body.control_robot(np.zeros(16))
    body.prepare_policy_control()
    body.robot.gripper_states = lambda: ([np.nan, 0.0], 1)
    with pytest.raises(RuntimeError, match='finite'):
        body.prepare_policy_control()
    with pytest.raises(RuntimeError, match='prepare_policy_control'):
        body.control_robot(np.zeros(16))
    assert commands == []


def test_gripper_rate_divider_preserved(robot):
    body, commands = robot
    body.prepare_policy_control()
    body.config['gripper_freq'] = 2
    for left in (0.2, 0.4, 0.6):
        action = np.zeros(16)
        action[14] = left
        body.control_robot(action)
    assert [values[0] for kind, values in commands if kind == 'gripper'] == [0.2, 0.6]


@pytest.mark.parametrize('value', [-0.2, 0.25, 0.5, 0.75, 1.2])
def test_right_gripper_mapping_can_be_toggled(robot, value):
    body, commands = robot
    body.prepare_policy_control()
    action = np.zeros(16)
    action[14:16] = [0.3, value]
    original = action.copy()
    clipped = float(np.clip(value, 0, 1))
    for enabled in (False, True, False):
        body.set_right_gripper_quartic_enabled(enabled)
        body.control_robot(action)
        expected = clipped**4 / (clipped**4 + (1-clipped)**4) if enabled else clipped
        assert commands[-1][1] == pytest.approx([0.3, expected])
        np.testing.assert_array_equal(action, original)


def test_gripper_mapping_rejects_non_boolean_setting(robot):
    body, _ = robot
    with pytest.raises(ValueError, match='boolean'):
        body.set_right_gripper_quartic_enabled('false')


def test_left_arm_keeps_reset_target_across_predictions_and_resume(robot):
    body, commands = robot
    body.config['hold_left_arm'] = True
    for target in (np.arange(14) / 20, np.arange(14) / 30):
        body.execute_action({'arm': target.tolist()})
        for prediction in (np.ones(16), np.full(16, -0.5)):
            body.prepare_policy_control()
            body.control_robot(prediction)
            np.testing.assert_allclose(commands[-2][1][:7], target[:7])
            np.testing.assert_allclose(commands[-2][1][7:], prediction[7:14])
            assert prediction[0] == prediction[-1]


def test_left_arm_latches_feedback_once_without_reset(robot):
    body, commands = robot
    body.config['hold_left_arm'] = True
    body.robot.arm_joint_states = lambda: (np.arange(14) / 20, 1)
    body.prepare_policy_control()
    body.control_robot(np.ones(16))
    body.robot.arm_joint_states = lambda: (np.zeros(14), 2)
    body.control_robot(np.zeros(16))
    np.testing.assert_allclose(commands[-2][1][:7], np.arange(7) / 20)


def test_delay_holds_gripper_but_not_arm_and_resume_clears_queue(robot, monkeypatch):
    body, commands = robot
    now = [0.0]
    monkeypatch.setattr(time, 'monotonic', lambda: now[0])
    body.prepare_policy_control()
    action = np.ones(16)
    body.control_robot(action, gripper_delay_s=.2)
    assert [kind for kind, _ in commands] == ['arm']
    now[0] = .2
    body.control_robot(np.zeros(16), gripper_delay_s=.2)
    assert commands[-1] == ('gripper', [1.0, 1.0])
    np.testing.assert_array_equal(commands[-2][1], np.zeros(14))
    body.prepare_policy_control()
    now[0] = .3
    commands.clear()
    body.control_robot(np.zeros(16), gripper_delay_s=.2)
    assert [kind for kind, _ in commands] == ['arm']
