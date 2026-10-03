"""Offline regression checks for the package pose and Web reset routing."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from conf.robots_conf import RobotType, get_agibot_g1_config


# Independent reference copied from the original package recovery script.
ARM = [
    -1.003602, 0.565485, 0.273005, -1.204992, 0.682469, 1.399298, -0.176315,
    1.074222, -0.611064, -0.279427, 1.283814, -0.730387, -1.495430, 0.187605,
]


@pytest.mark.parametrize('source', ['python', 'yaml'])
def test_package_defaults_match_original_pose_and_sdk_units(source):
    if source == 'python':
        layout = get_agibot_g1_config().to_dict()['action_layout']
    else:
        path = Path(__file__).resolve().parents[1] / 'conf/lingbot_package.yaml'
        layout = yaml.safe_load(path.read_text())['robots']['agibot_g1']['action_layout']
    arms = layout['arm']['presets']
    assert arms['left']['Default'] + arms['right']['Default'] == pytest.approx(ARM)
    assert layout['head']['presets']['Default'] == pytest.approx([-0.257285, 0.428170])
    pitch, lift_cm = layout['waist']['presets']['Default']
    assert [pitch, lift_cm / 100] == pytest.approx([0.491126, 0.447520])
    grippers = layout['gripper']['presets']
    assert grippers['left']['Default'] == [0.0]
    assert grippers['right']['Default'][0] * 120 == pytest.approx(0.217333)
    assert layout['wheel']['presets']['Default'] == [0, 0]


@pytest.mark.parametrize('robot_type', [RobotType.AGIBOT_G1, 'agibot_g1', RobotType.MOCK])
def test_web_reset_ignores_stale_manual_targets_for_g1(monkeypatch, robot_type):
    from web_client import server

    events = []
    robot = SimpleNamespace(
        reset_robot=Mock(side_effect=lambda **kw: events.append('default')),
        _control_robot=Mock(side_effect=lambda data: events.append('manual')),
    )
    client = SimpleNamespace(
        reset=Mock(side_effect=lambda: events.append('clear')),
        realtime_data_manager=SimpleNamespace(avg_infer_time=0),
    )
    state = server.ClientState()
    state.config = SimpleNamespace(robots=SimpleNamespace(type=robot_type))
    state.running = True
    monkeypatch.setattr(server, 'client_state', state)
    monkeypatch.setattr(server, '_require_runtime', lambda _: (client, robot))
    monkeypatch.setattr(server, '_thread_state', lambda _: {'control_running': True})
    monkeypatch.setattr(server, '_pause_vla_client', lambda _: events.append('pause'))
    monkeypatch.setattr(server, '_broadcast_to_web', AsyncMock())
    # Simulate an old browser still sending the old 27 cm reset target.
    request = server.ManualControlRequest(waist=[0.4012, 27.0], l_arm=[0] * 7)
    result = asyncio.run(server._client_control_reset(request))
    assert result['status'] == 'ok'
    assert state.paused
    if robot_type in (RobotType.AGIBOT_G1, 'agibot_g1'):
        robot.reset_robot.assert_called_once_with(mode='default')
        robot._control_robot.assert_not_called()
        assert events == ['pause', 'default', 'clear']
    else:
        robot.reset_robot.assert_not_called()
        assert events == ['pause', 'manual', 'clear']
