"""Test actual smoother methods without importing hardware/scipy dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np


class Config(dict):
    __getattr__ = dict.__getitem__


def smoother(enabled):
    path = Path(__file__).resolve().parents[1] / 'client/core/intra_chunk_smoother.py'
    cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef))
    names = {'_gripper_traj_fitting_batch', '_joint_traj_fitting_batch', '_traj_fitting'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for method in methods:
        method.decorator_list = []
    ns = {'np': np}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), ns)
    obj = SimpleNamespace(config=Config(gripper_zero_order_hold=enabled, filter_window_size=4,
        min_gripper_action_threshold=.05, max_gripper_action_threshold=.95, fitting_deg=4),
        action_layout={'arm': {'start': 0, 'end': 14, 'policy': 'gradual'},
                       'gripper': {'start': 14, 'end': 16, 'policy': 'stepwise'}})
    for name in names:
        setattr(obj, name, ns[name].__get__(obj))
    return obj


def test_future_change_does_not_leak_and_exact_boundary_uses_new_point():
    obj = smoother(True)
    t = np.arange(10, dtype=float)
    q = np.ones((2, 10)); q[:, 5:] = 0
    out, v, a = obj._gripper_traj_fitting_batch(t, q, 0, 9, .25)
    assert np.all(out[:, :20] == 1)
    assert np.all(out[:, 20:] == 0)
    assert np.all(v == 0) and np.all(a == 0)
    obj.config['gripper_zero_order_hold'] = False
    old, _, _ = obj._gripper_traj_fitting_batch(t, q, 0, 9, .25)
    assert np.any(old[:, :20] < 1)


def test_no_threshold_snap_and_empty_or_single_point():
    obj = smoother(True)
    q = np.array([[.02], [.98]])
    out, _, _ = obj._gripper_traj_fitting_batch([0], q, 0, 1, .25)
    np.testing.assert_array_equal(out, np.repeat(q, 4, axis=1))
    empty, _, _ = obj._gripper_traj_fitting_batch([], np.empty((2, 0)), 0, 0, .25)
    assert empty.shape == (2, 0)


def test_fitting_arm_unchanged_and_grippers_match_raw_hold():
    t = np.arange(50) / 30
    q = np.random.default_rng(4).uniform(0, 1, (16, 50))
    original = q.copy()
    results = [smoother(enabled)._traj_fitting(t, q, t[0], t[-1], .00375,
               list(range(14)), [14, 15]) for enabled in (False, True)]
    for old, new in zip(results[0][:3], results[1][:3]):
        np.testing.assert_array_equal(old[:14], new[:14])
    indices = np.searchsorted(t, results[1][3], side='right') - 1
    np.testing.assert_array_equal(results[1][0][14:], q[14:, indices])
    np.testing.assert_array_equal(q, original)
