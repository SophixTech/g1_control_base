"""Offline vision + control scheduling tests. No robot, network or model is started."""
import threading
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from client.core.conveyor_gate import ConveyorGate
from client.core.conveyor_control import ConveyorControlMixin


CONFIG = dict(enabled=True, reference_size=[200,100], rois=[[i*40,0,40,40] for i in range(5)],
              stop_delay_s=2., resume_stable_s=.3, frame_timeout_s=.5, detect_hz=10)


def frame(count):
    image = np.zeros((100,200,3), np.uint8)
    for i in range(count):
        image[10:25, i*40+10:i*40+25] = (0,0,255)
    return image


def feed(gate, count, now):
    gate.update(frame(count), source_time=now, now=now)
    return gate.tick(now)


def test_detection_raw_bgr_and_individual_rois():
    gate = ConveyorGate(CONFIG)
    gate.update(frame(3), now=10)
    assert gate.visible == 3
    assert [p['visible'] for p in gate.points] == [True,True,True,False,False]
    assert gate.preview
    # Blue objects are not red, nor are isolated one-pixel speckles.
    image = frame(5)[:,:,::-1].copy()
    image[3,3] = (0,0,255)
    gate.update(image, now=11)
    assert gate.visible == 0


def test_wraparound_red_and_scaled_frame():
    gate = ConveyorGate(CONFIG)
    hsv = cv2.cvtColor(frame(4), cv2.COLOR_BGR2HSV)
    hsv[hsv[:,:,1] > 0, 0] = 179
    image = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    gate.update(cv2.resize(image,(400,200),interpolation=cv2.INTER_NEAREST), now=10)
    assert gate.visible == 4


def test_start_wait_delay_cancel_and_resume():
    gate = ConveyorGate(CONFIG)
    gate.arm()
    assert feed(gate,2,10) is None and gate.phase == 'waiting'
    assert feed(gate,3,11) is None
    assert feed(gate,3,11.4) == 'resume'
    gate.phase = 'running'
    assert feed(gate,2,12) is None and gate.deadline == 14
    assert feed(gate,2,12.5) is None and gate.deadline == 14
    assert feed(gate,3,13) is None and gate.deadline is None
    feed(gate,2,14)
    assert feed(gate,2,16.1) == 'pause'
    assert gate.authorized and gate.phase == 'waiting'
    feed(gate,3,17)
    assert feed(gate,3,17.4) == 'resume'
    gate.disarm()
    assert feed(gate,5,18) is None and not gate.authorized


def test_stale_camera_stops_without_delay_and_cancels_resuming():
    gate = ConveyorGate(CONFIG)
    gate.arm();feed(gate,5,10);feed(gate,5,10.4)
    assert gate.phase == 'resuming'
    assert gate.tick(11) == 'pause'
    feed(gate,5,12);feed(gate,5,12.4);gate.phase = 'running'
    assert gate.tick(13) == 'pause'


def test_disabled_gate_and_missing_rois():
    gate = ConveyorGate()
    gate.update(frame(5),now=10)
    assert gate.tick(11) is None and gate.last_frame is None
    with pytest.raises(ValueError,match='5'):
        ConveyorGate({'enabled':True}).arm()
    with pytest.raises(ValueError):
        ConveyorGate({**CONFIG,'detect_hz':0})


class FakeClient(ConveyorControlMixin):
    def __init__(self):
        self.conveyor_gate = ConveyorGate(CONFIG)
        self._conveyor_transition = threading.RLock()
        self._inference_execution_lock = threading.Lock()
        self._conveyor_dirty = False
        self._conveyor_epoch = 0
        self._conveyor_primed = False
        self.is_control_thread_running = False
        self.is_observe_thread_running = True
        self.is_inference_thread_running = False
        self.calls = []
        self.realtime_data_manager = SimpleNamespace(action_lock=threading.Lock(),action_chunk_fitted=None,clear=self.clear)
        self.robot = SimpleNamespace(check_control_health=lambda:None,prepare_policy_control=lambda:None)
        self.task_language_manager = SimpleNamespace(new_task=lambda:self.calls.append('new_task'))
        self.logger = SimpleNamespace(info=lambda *args:None)
    def clear(self):
        self.realtime_data_manager.action_chunk_fitted=None
        self.calls.append('clear')
    def _clear_raw_observe_queue(self):
        self.calls.append('clear_observations')
    def _stop_control_direct(self):
        self.is_control_thread_running=False
        self.calls.append('stop')
    def stop_inference(self):
        self.is_inference_thread_running=False
    def start_inference(self):
        self.is_inference_thread_running=True
        self.calls.append('infer')
    def _start_control_direct(self,new_task=True):
        self.is_control_thread_running=True
        self.calls.append(('start',new_task))


@pytest.fixture
def clock(monkeypatch):
    now=[10.]
    monkeypatch.setattr('client.core.conveyor_gate.time.perf_counter',lambda:now[0])
    return now


def ready(client,clock):
    for t in (11.,11.4):
        clock[0]=t
        client.conveyor_gate.update(frame(3),source_time=t)
        client._conveyor_step()


def test_inflight_old_chunk_cleared_before_fresh_inference(clock):
    client=FakeClient();client._arm_conveyor()
    client._inference_execution_lock.acquire()
    ready(client,clock)
    assert not client.is_control_thread_running
    assert not client.is_inference_thread_running
    # A response from before pause arrives while its request owns the inference lock.
    client.realtime_data_manager.action_chunk_fitted='old'
    client._inference_execution_lock.release()
    client._conveyor_step()
    assert client.realtime_data_manager.action_chunk_fitted is None
    assert client.is_inference_thread_running and not client.is_control_thread_running
    client.realtime_data_manager.action_chunk_fitted='fresh'
    client._conveyor_step()
    assert client.is_control_thread_running
    assert ('start',False) in client.calls
    assert client.calls.count('new_task') == 1


def test_manual_stop_during_inflight_resume_cannot_restart(clock):
    client=FakeClient();client._arm_conveyor()
    client._inference_execution_lock.acquire();ready(client,clock)
    client._cancel_conveyor()
    client.realtime_data_manager.action_chunk_fitted='old'
    client._inference_execution_lock.release()
    clock[0]=11.5;client._conveyor_step()
    assert not client.control_requested
    assert not client.is_inference_thread_running
    assert not any(isinstance(c,tuple) and c[0]=='start' for c in client.calls)


def test_waiting_is_still_manual_stop_and_edit_is_blocked(clock):
    client=FakeClient();client._arm_conveyor()
    assert client.control_requested and not client.is_control_thread_running
    with pytest.raises(ValueError,match='Control Stop'):
        client.set_conveyor_config({**CONFIG,'enabled':False})
    client._cancel_conveyor();client._conveyor_step()
    client.set_conveyor_config({**CONFIG,'enabled':False})
    assert not client.conveyor_gate.enabled


def test_fault_never_auto_recovers(clock):
    client=FakeClient();client._arm_conveyor();ready(client,clock)
    client._cancel_conveyor('feedback invalid')
    for t in (12.,13.):
        clock[0]=t;client.conveyor_gate.update(frame(5),source_time=t);client._conveyor_step()
    assert not client.control_requested
    assert client.conveyor_gate.phase=='fault'
    assert client.conveyor_gate.error=='feedback invalid'


def test_disabled_coordinator_leaves_existing_execution_alone(clock):
    client=FakeClient();client.conveyor_gate=ConveyorGate()
    client.is_control_thread_running=client.is_inference_thread_running=True
    client._conveyor_step()
    assert client.calls==[]
    assert client.is_control_thread_running and client.is_inference_thread_running


def test_real_vla_disabled_start_stop_use_original_paths():
    from client.core.vla_client import VLAClient
    client=SimpleNamespace(conveyor_gate=ConveyorGate(), calls=[])
    client._start_control_direct=lambda:client.calls.append('original_start')
    client._stop_control_direct=lambda:client.calls.append('original_stop')
    VLAClient.start_control(client);VLAClient.stop_control(client)
    assert client.calls==['original_start','original_stop']


def test_real_vla_enabled_start_stop_use_gate():
    from client.core.vla_client import VLAClient
    client=SimpleNamespace(conveyor_gate=ConveyorGate(CONFIG), calls=[])
    client._arm_conveyor=lambda:client.calls.append('arm')
    client._cancel_conveyor=lambda:client.calls.append('cancel')
    VLAClient.start_control(client);VLAClient.stop_control(client)
    assert client.calls==['arm','cancel']


def test_realtime_clear_rejects_old_observation():
    import time
    from conf.client_conf import get_rdm_config
    from client.core.realtime_data_manager import RealtimeDataManager
    rdm=RealtimeDataManager(get_rdm_config())
    old=time.perf_counter()-1
    rdm.action_chunk_fitted=np.ones((16,50))
    rdm.clear()
    assert rdm.action_chunk_fitted is None
    assert not rdm.add_observe_data({'ref_timestamp':1},source_time=old)


def test_web_gate_config_toggle_and_manual_stop_semantics(monkeypatch,clock):
    import asyncio
    from fastapi import HTTPException
    from conf.client_conf import get_client_config
    from web_client import server
    config=get_client_config()
    client=FakeClient()
    monkeypatch.setattr(server.client_state,'config',config)
    monkeypatch.setattr(server.client_state,'vla_client',client)
    monkeypatch.setattr(server.client_state,'robot',None)
    monkeypatch.setattr(server.client_state,'running',False)
    request=server.ConfigPatchRequest(patch={'vision.conveyor_gate.enabled':True,
                                            'vision.conveyor_gate.rois':CONFIG['rois'],
                                            'vision.conveyor_gate.reference_size':[200,100]})
    asyncio.run(server.patch_config(request))
    assert config.vision.conveyor_gate.enabled
    client._arm_conveyor()
    assert asyncio.run(server.conveyor_status())['authorized']
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.patch_config(server.ConfigPatchRequest(patch={'vision.conveyor_gate.enabled':False})))
    assert exc.value.status_code==409 and config.vision.conveyor_gate.enabled
    calls=[]
    async def broadcast(message): calls.append(message)
    monkeypatch.setattr(server,'_broadcast_to_web',broadcast)
    monkeypatch.setattr(server,'_stop_control',lambda v:v._cancel_conveyor())
    monkeypatch.setattr(server,'_status_payload',lambda *args,**kwargs:{'control_requested':client.control_requested})
    asyncio.run(server._bg_toggle_control_and_broadcast(client))
    assert not client.control_requested
    assert calls[-1]['data']['control_requested'] is False


def test_real_control_start_rechecks_stop_after_preparation():
    from client.core.vla_client import VLAClient
    gate=ConveyorGate(CONFIG);gate.arm()
    calls=[]
    client=SimpleNamespace(is_control_thread_running=False,_control_execution_lock=threading.Lock(),
                           conveyor_gate=gate,robot=SimpleNamespace(
                               prepare_policy_control=lambda:gate.disarm(),
                               resume_controls=lambda:calls.append('resume')))
    VLAClient._start_control_direct(client,new_task=False)
    assert not client.is_control_thread_running and not calls


def test_stop_during_initial_prepare_cannot_arm(clock):
    client=FakeClient()
    def prepare():
        # Simulate the immediate cancellation part of a concurrent manual Stop.
        client._conveyor_epoch+=1
        client.conveyor_gate.disarm()
    client.robot.prepare_policy_control=prepare
    client._arm_conveyor()
    assert not client.conveyor_gate.authorized
    assert 'new_task' not in client.calls


def test_worker_fault_is_checked_without_clearing_or_motion():
    import queue
    from client.robots.robot_proxy import _RobotWorker
    failed=threading.Event()
    worker=SimpleNamespace(_control_failed=failed,_robot_command_lock=threading.Lock(),
                           _resp_queue=queue.Queue())
    _RobotWorker._handle_command(worker,('call',1,'check_control_health',(),{}))
    assert worker._resp_queue.get()==(1,True,True)
    failed.set()
    _RobotWorker._handle_command(worker,('call',2,'check_control_health',(),{}))
    _, success, error=worker._resp_queue.get()
    assert not success and isinstance(error,RuntimeError)
    assert failed.is_set()


def test_control_endpoint_accepts_gate_waiting_without_inference(monkeypatch):
    import asyncio
    from web_client import server
    client=FakeClient();client.conveyor_gate.arm()
    monkeypatch.setattr(server.client_state,'running',True)
    monkeypatch.setattr(server.client_state,'vla_client',client)
    seen=[]
    async def toggle(vla):
        seen.append(vla.control_requested)
        vla._cancel_conveyor()
    monkeypatch.setattr(server,'_bg_toggle_control_and_broadcast',toggle)
    async def run():
        result=await server.start_control_only()
        await asyncio.sleep(0)
        return result
    assert asyncio.run(run())['status']=='ok'
    assert seen==[True] and not client.control_requested
