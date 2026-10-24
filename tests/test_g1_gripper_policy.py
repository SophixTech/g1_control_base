"""Exercise G1 command methods offline, without importing the hardware SDK."""
import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def robot():
    source = Path(__file__).resolve().parents[1] / 'client/robots/agibot_g1/body_robot.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'RobotBody')
    names = {'prepare_policy_control', 'control_robot'}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {'np': np}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), namespace)
    commands = []
    body = SimpleNamespace(
        _policy_control_ready=False, gripper_count=0, config={'gripper_freq': 1},
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
