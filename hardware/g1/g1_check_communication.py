#!/usr/bin/env python3
"""Read-only Cosine subscriptions: no command publishers or mode requests."""
import argparse
import json
import math
import os
import sys
import threading
import time


def fresh(stamp_ns, now_ns, max_age_s=0.5):
    return stamp_ns > 0 and abs(now_ns - stamp_ns) <= max_age_s * 1e9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=15)
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error('--timeout must be in (0, 120]')
    from cosine_bus.agibotdds_py3 import agibotdds
    from a2d_sdk.robot import CosineCamera
    from sensor_msgs_pb.msg.JointState_pb2 import JointState
    from genie_msgs_pb.msg.WholeBodyStatus_pb2 import WholeBodyStatus
    from genie_msgs_pb.msg.EndState_pb2 import EndState

    lock = threading.Lock()
    records = {}
    counts = {}

    def save(name, stamp, details):
        with lock:
            if stamp > records.get(name, {}).get('stamp_ns', 0):
                counts[name] = counts.get(name, 0) + 1
            records[name] = dict(stamp_ns=stamp, **details)

    def callback(name):
        def receive(msg):
            stamp = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            details = {}
            if name == 'arm':
                values = list(msg.position)
                details = {'joint_count': len(values),
                           'valid': len(values) == 14 and all(math.isfinite(x) for x in values)}
            elif name == 'status':
                details['flags'] = {field.name: getattr(msg, field.name)
                                    for field in msg.DESCRIPTOR.fields
                                    if field.name.endswith(('_error', '_estop', '_control'))}
            save(name, stamp, details)
        return receive

    node = agibotdds.Node('openrail_communication_readonly')
    subscribers = [node.create_subscriber(topic, message, agibotdds.qos(depth=5), callback(name))
                   for name, topic, message in [
                       ('arm', '/hal/arm_joint_state', JointState),
                       ('status', '/hal/whole_body_status', WholeBodyStatus),
                       ('left_gripper', '/hal/left_ee_data', EndState),
                       ('right_gripper', '/hal/right_ee_data', EndState)]]
    camera_names = ('head', 'hand_left', 'hand_right')
    cameras = CosineCamera(list(camera_names))
    expected = ('arm', 'status', 'left_gripper', 'right_gripper', *camera_names)
    deadline = time.monotonic() + args.timeout
    ready = False
    while time.monotonic() < deadline:
        for name in camera_names:
            frame, stamp = cameras.get_latest_image(name)
            if frame is not None and stamp is not None:
                save(name, int(stamp), {'shape': list(frame.shape), 'valid': frame.ndim == 3 and frame.size > 0})
        with lock:
            now = time.time_ns()
            ready = all(name in records and counts.get(name, 0) >= 2
                        and fresh(records[name]['stamp_ns'], now)
                        and records[name].get('valid', True) for name in expected)
        if ready:
            break
        time.sleep(0.05)
    with lock:
        now = time.time_ns()
        report = {name: dict(records.get(name, {}), samples=counts.get(name, 0),
                            fresh=fresh(records.get(name, {}).get('stamp_ns', 0), now))
                  for name in expected}
    print(json.dumps({'communication_ok': ready, 'read_only': True,
                      'note': 'Communication check only; does not certify safe motion or exclusive control.',
                      'streams': report}, indent=2), flush=True)
    return 0 if ready else 1


if __name__ == '__main__':
    try:
        result = main()
    except Exception as exc:
        print(f'Communication check failed: {exc}', file=sys.stderr, flush=True)
        result = 1
    # The vendor native subscriber teardown can hang at interpreter shutdown.
    # This standalone subscriber has no buffered output or control publishers.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(result)
