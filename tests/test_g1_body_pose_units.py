"""Check request units offline; no SDK initialization or robot connections."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_head_request_preserves_waist_in_service_units_without_mutating_feedback():
    path = Path(__file__).resolve().parents[1] / 'client/robots/agibot_g1/sdk_robot.py'
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef))
    namespace = {'math': math, 'BodyPose_Request': lambda: SimpleNamespace(joint_states=[])}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    cache = [-11.96, 25.0, 0.5385738312687142, 0.4463360595703125]
    original = list(cache)
    sent = []
    robot = SimpleNamespace(
        _body_pose_joint_states=cache,
        _body_pose_client=SimpleNamespace(send_request=lambda request: sent.append(request)),
    )
    for _ in range(2):
        namespace['move_head'](robot, [-0.20881313, 0.43633231])
    assert cache == original
    assert len(sent) == 2
    for request in sent:
        assert request.joint_flag == 3
        assert request.joint_states == pytest.approx([
            -11.96411134, 25.0, 30.858009, 44.63360595703125,
        ], abs=1e-5)
        # HAL converts BodyPose centimetres into millimetres.
        assert request.joint_states[3] * 10 == pytest.approx(446.33605957)
