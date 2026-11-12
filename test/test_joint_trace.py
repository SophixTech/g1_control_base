import json
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
from ml_collections import ConfigDict

from client.core.joint_trace import JointTrace
from client.core.realtime_data_manager import RealtimeDataManager
from client.core.vla_client import VLAClient
from client.robots.robot_proxy import _RobotWorker
from scripts.analyze_joint_trace import analyze, read_events, render_report


def test_trace_flushes_and_reports_drops_without_blocking_control(tmp_path):
    trace = JointTrace(tmp_path, 'client', 7, queue_size=2)
    # Simulate a stalled disk: the producer must never wait for the writer.
    entered, release = threading.Event(), threading.Event()
    real_file = trace._file

    class SlowFile:
        def write(self, data):
            entered.set()
            assert release.wait(2)
            return real_file.write(data)

        def flush(self):
            return real_file.flush()

        def close(self):
            return real_file.close()

    trace._file = SlowFile()
    trace.record('block')
    assert entered.wait(1)
    started = time.perf_counter()
    for i in range(100):
        trace.record('sample', q=i)
    assert time.perf_counter() - started < 0.1
    assert trace.dropped > 0
    release.set()
    trace.close()
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert rows[-1]['event'] == 'stream_end'
    assert rows[-1]['dropped'] == trace.dropped


def test_fitted_sample_keeps_its_chunk_identity_when_new_raw_chunk_arrives():
    manager = RealtimeDataManager(ConfigDict({'max_len': 10, 'observe_fps_window_size': 2}))
    manager.update_action_chunk_raw([[1], [2], [3]], [0, 1, 2])
    manager.update_action_chunk_fitted(np.array([[1., 2., 3.]]), np.zeros((1, 3)),
                                      np.zeros((1, 3)), np.array([0., 1., 2.]), 0,
                                      trace_context={'chunk_id': 'first'})
    manager.update_action_chunk_raw([[9], [10], [11]], [0, 1, 2])
    values, context = manager.get_action_fitted(with_trace=True)
    assert values[0][0] == 2
    assert context == {'chunk_id': 'first', 'fitted_index': 1, 'planned_offset_s': 1.}
    manager.clear()
    assert manager.get_action_fitted(with_trace=True) == ((None, None, None, None), None)


def test_low_speed_logs_raw_model_positions_without_scaling_angles(tmp_path):
    client = VLAClient.__new__(VLAClient)
    client.joint_trace = JointTrace(tmp_path, 'client', 7)
    client.observe_period = 1 / (30 * 0.005)
    client.config = SimpleNamespace(controller=SimpleNamespace(speed=.005, period=3.75),
                                    rdm=SimpleNamespace(mode='async'),
                                    intra_chunk=SimpleNamespace(intra_chunk_mode='interpolation'),
                                    inter_chunk=SimpleNamespace(inter_chunk_mode='min_jerk'))
    actions = np.arange(50 * 16, dtype=float).reshape(50, 16)
    data = dict(type='vla_action', pred_action=actions, ref_timestamp=100,
                loc_timestamp=1., _trace={'chunk_id': 'model-1', 'request_ns': 10, 'response_ns': 20})
    client._process_action_chunk(data)
    client.joint_trace.close()
    records = [json.loads(line) for line in client.joint_trace.path.read_text().splitlines()]
    row = next(r for r in records if r['event'] == 'model_chunk')
    assert row['q'] == list(actions[:, 7])
    assert row['raw_period_s'] == client.observe_period
    assert row['chunk_id'] == 'model-1'


def test_worker_records_superseded_commands_and_passes_latest_context():
    worker = _RobotWorker.__new__(_RobotWorker)
    worker._control_queue = queue.Queue()
    worker._control_queue.put((0, np.array([1]), {'command_id': 1}))
    worker._control_queue.put((0, np.array([2]), {'command_id': 2}))
    worker._control_stop = threading.Event()
    worker._control_failed = threading.Event()
    worker._robot_command_lock = threading.Lock()
    worker._control_epoch = SimpleNamespace(value=0, get_lock=threading.Lock)
    worker._control_error_queue = queue.Queue()
    discarded, received = [], []

    def control(action, trace_context):
        received.append((action.tolist(), trace_context))
        worker._control_stop.set()

    worker._robot = SimpleNamespace(control_robot=control,
                                    _joint_trace=SimpleNamespace(record=lambda event, **kw: discarded.append((event, kw))))
    worker._control_loop()
    assert received == [([2], {'command_id': 2})]
    assert discarded == [('command_discard', {'command_id': 1, 'reason': 'superseded'})]


def sample_events():
    def event(kind, t, **kw):
        return dict(event=kind, mono_ns=int(t * 1e9), **kw)
    events = [event('stream_start', 0, joint=7),
              event('model_chunk', .3, chunk_id='a', q=[0., 1., 2.], raw_period_s=1.,
                    observation_pc_s=0., speed=1.),
              event('control_start', .4),
              event('command_submit', .49, command_id=1, chunk_id='a', q=.7, submit_ns=490_000_000),
              event('command_submit', .50, command_id=2, chunk_id='a', q=.8, submit_ns=500_000_000),
              event('command_discard', .51, command_id=1, reason='superseded'),
              event('sdk_command', .52, command_id=2, chunk_id='a', q=.8,
                    submit_ns=500_000_000, send_start_ns=510_000_000, send_end_ns=520_000_000,
                    planned_offset_s=.5, fitted_index=1),
              event('control_stop', 1.)]
    for i, (t, q) in enumerate([(.3, 0.), (.4, 0.), (.5, 0.), (.55, 0.), (.6, .003), (.65, .004), (.7, .005)]):
        events.append(event('feedback', t, q=q, device_stamp_ns=1_700_000_000_000_000_000 + i * 50_000_000))
    return sorted(events, key=lambda e: e['mono_ns'])


def test_report_matches_same_chunk_and_never_labels_queue_submission_as_execution(tmp_path):
    result = analyze(sample_events())
    assert result['summary']['sdk_calls_returned'] == 1
    assert result['summary']['explicitly_discarded'] == 1
    assert result['summary']['submitted_without_terminal_record'] == 0
    row = result['rows'][0]
    assert row['model_linear_reference_rad'] == .5
    assert np.isclose(row['fitted_minus_model_rad'], .3)
    assert row['sdk_minus_fitted_rad'] == 0
    assert row['queue_delay_ms'] == 10
    assert row['sdk_call_ms'] == 10
    onset = result['summary']['motion_onsets'][0]
    assert onset['first_moving_seen_ns'] == 600_000_000
    assert onset['last_still_seen_ns'] == 550_000_000
    page = render_report(tmp_path, result, ['test incomplete capture'])
    assert '<script src=' not in page
    assert 'test incomplete capture' in page
    assert 'SDK 调用返回不代表电机收到或开始执行' in page


def test_no_claimed_motion_onset_when_already_moving():
    events = sample_events()
    for e in events:
        if e['event'] == 'feedback' and e['mono_ns'] < 510_000_000:
            e['q'] = e['mono_ns'] / 1e9
    onset = analyze(events)['summary']['motion_onsets'][0]
    assert onset['status'].startswith('unknown')
    assert 'first_moving_seen_ns' not in onset


def test_truncated_capture_warns_instead_of_claiming_complete(tmp_path):
    (tmp_path / 'client.jsonl').write_text(json.dumps(sample_events()[0]) + '\n{"event":')
    events, warnings = read_events(tmp_path)
    assert len(events) == 1
    assert any('incomplete or invalid JSON' in w for w in warnings)
    assert any('no clean end marker' in w for w in warnings)
    assert any('Missing robot.jsonl' in w for w in warnings)


def test_sdk_failure_is_not_reported_as_successful_execution():
    events = sample_events()
    sent = next(e for e in events if e['event'] == 'sdk_command')
    sent['event'] = 'sdk_error'
    sent['error'] = 'injected failure'
    result = analyze(events)
    assert result['summary']['sdk_calls_returned'] == 0
    assert result['summary']['sdk_errors'] == 1
    assert result['summary']['submitted_without_terminal_record'] == 0
    assert result['summary']['motion_onsets'][0]['status'] == 'no successful SDK command'


def test_write_failure_disables_trace_and_reports_error(tmp_path):
    trace = JointTrace(tmp_path, 'client', 7)
    real_file = trace._file

    class BrokenFile:
        def write(self, _):
            raise OSError('injected disk full')

        def flush(self):
            pass

        def close(self):
            real_file.close()

    trace._file = BrokenFile()
    trace.record('sample', q=1.)
    deadline = time.monotonic() + 1
    while not trace.error and time.monotonic() < deadline:
        time.sleep(.01)
    assert 'disk full' in trace.error
    assert trace.record('sample', q=2.) is False
    trace.close()


def test_gripper_csv_preserves_chunks_and_raw_feedback_units(tmp_path):
    from scripts.export_gripper_trace import export
    import csv
    for stream in ('client', 'robot'):
        trace = JointTrace(tmp_path, stream, 15)
        if stream == 'client':
            trace.record('model_chunk', chunk_id='a', q=[.2, .8], raw_period_s=.1)
        else:
            trace.record('feedback', q=105., sdk_pair_stamp_ns=42, stamp_source='left_gripper')
        trace.close()
    with export(tmp_path).open() as f:
        rows = list(csv.DictReader(f))
    model = [r for r in rows if r['event'] == 'model_chunk']
    assert [float(r['q']) for r in model] == [.2, .8]
    assert float(model[1]['planned_offset_s']) == .1
    feedback = next(r for r in rows if r['event'] == 'feedback')
    assert float(feedback['q']) == 105.
    assert feedback['stamp_source'] == 'left_gripper'
