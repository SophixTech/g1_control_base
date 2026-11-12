"""Offline lifecycle regressions: fake constructors, no SDK or model server."""
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def runtime(monkeypatch):
    from web_client import server
    from client.core import vla_client
    state = server.ClientState()
    state.config = SimpleNamespace(robots=SimpleNamespace(type=SimpleNamespace(value='fake'), fake={}),
                                   vla_zmq={}, rdm={}, inter_chunk={}, intra_chunk={}, language={})
    monkeypatch.setattr(server, 'client_state', state)
    robot = Mock()
    monkeypatch.setattr(server, '_create_robot', Mock(return_value=robot))
    for name in ['ZMQClient', 'RealtimeDataManager', 'InterChunkFuser',
                 'IntraChunkSmoother', 'TaskLanguageManager']:
        monkeypatch.setattr(server, name, Mock())
    factory = Mock(return_value=Mock())
    monkeypatch.setattr(vla_client, 'VLAClient', factory)
    return server, state, factory, robot


def test_concurrent_initialization_creates_one_client(runtime):
    server, state, factory, robot = runtime
    entered, release = threading.Event(), threading.Event()
    def create(*args):
        entered.set()
        assert release.wait(3)
        return robot
    server._create_robot.side_effect = create
    with ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(server._ensure_vla_client_created)
        assert entered.wait(3)
        rest = [pool.submit(server._ensure_vla_client_created) for _ in range(7)]
        # Status reads must remain available while SDK initialization waits.
        assert state.lock.acquire(timeout=1)
        state.lock.release()
        release.set()
        results = [first.result()] + [f.result() for f in rest]
    assert all(r is results[0] for r in results)
    assert server._create_robot.call_count == factory.call_count == 1


def test_failed_creation_can_retry_and_closes_robot(runtime):
    server, state, factory, robot = runtime
    factory.side_effect = [RuntimeError('init failed'), Mock()]
    with pytest.raises(RuntimeError, match='init failed'):
        server._ensure_vla_client_created()
    robot.close.assert_called_once()
    assert state.vla_client is None
    assert server._ensure_vla_client_created() is state.vla_client


def test_shutdown_blocks_new_creation_and_closes_existing(runtime):
    server, state, factory, robot = runtime
    client = server._ensure_vla_client_created()
    state.shutting_down = True
    server._cleanup()
    client.close.assert_called_once()
    with pytest.raises(RuntimeError, match='shutting down'):
        server._ensure_vla_client_created()
    assert factory.call_count == 1


def test_cleanup_waits_for_inflight_creation(runtime):
    server, state, factory, robot = runtime
    entered, release = threading.Event(), threading.Event()
    def create(*args):
        entered.set()
        assert release.wait(3)
        return robot
    server._create_robot.side_effect = create
    with ThreadPoolExecutor(max_workers=2) as pool:
        init = pool.submit(server._ensure_vla_client_created)
        assert entered.wait(3)
        close = pool.submit(server._cleanup)
        assert not close.done()
        release.set()
        client = init.result()
        close.result()
    client.close.assert_called_once()
    assert state.vla_client is None


def test_occupied_visualization_port_reports_error_without_killing(monkeypatch, caplog):
    import os
    import socket
    from client.core.visualize_server import VisualizeServer
    kill = Mock()
    monkeypatch.setattr(os, 'system', kill)
    monkeypatch.setattr(os, 'kill', kill)
    with socket.socket() as owner:
        owner.bind(('127.0.0.1', 0))
        owner.listen()
        config = SimpleNamespace(host='127.0.0.1', port=owner.getsockname()[1],
                                 max_size=1048576, ping_interval=20, ping_timeout=10)
        visual = VisualizeServer(config)
        visual.main_thread.join(timeout=3)
        assert not visual.main_thread.is_alive()
        assert 'Server error:' in caplog.text
        assert owner.fileno() >= 0
    kill.assert_not_called()
