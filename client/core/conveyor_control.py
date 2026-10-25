"""Client-side coordination for the optional conveyor gate; no hardware commands here."""
import threading

from client.core.conveyor_gate import ConveyorGate


class ConveyorControlMixin:
    def _init_conveyor(self):
        self.conveyor_gate = ConveyorGate(self.config.vision.get('conveyor_gate', {}))
        self._conveyor_transition = threading.RLock()
        self._conveyor_shutdown = threading.Event()
        self._conveyor_dirty = False
        self._conveyor_epoch = 0
        self._conveyor_primed = False
        self._conveyor_thread = threading.Thread(target=self._conveyor_loop, daemon=True, name='conveyor-gate')
        self._conveyor_thread.start()

    def set_conveyor_config(self, config):
        with self._conveyor_transition:
            if self.conveyor_gate.authorized or self.is_control_thread_running or self._conveyor_dirty:
                raise ValueError('请先 Control Stop，再修改红点检测配置')
            candidate = ConveyorGate(config)
            if candidate.config['rois']:
                candidate.validate()
            self.conveyor_gate = candidate

    @property
    def control_requested(self):
        return self.is_control_thread_running or self.conveyor_gate.authorized

    def _arm_conveyor(self):
        with self._conveyor_transition:
            if self.conveyor_gate.authorized:
                return
            if not self.is_observe_thread_running:
                raise ValueError('请先 Observe Start，再开启红点控制')
            self.conveyor_gate.validate()
            epoch = self._conveyor_epoch
            check = getattr(self.robot, 'check_control_health', None)
            if check:
                check()
            self.robot.prepare_policy_control()
            self._suspend_conveyor()
            with self.conveyor_gate.lock:
                if epoch != self._conveyor_epoch:
                    return
                self.task_language_manager.new_task()
                self.conveyor_gate.arm()
            self.logger.info('Conveyor armed; waiting for visible markers')

    def _suspend_conveyor(self):
        # Stop commands immediately. Never wait for GPU inference before stopping motion.
        self._stop_control_direct()
        self.stop_inference()
        self._conveyor_dirty = True
        self._conveyor_primed = False

    def _cancel_conveyor(self, error=None):
        if self.conveyor_gate.enabled:
            with self.conveyor_gate.lock:
                self._conveyor_epoch += 1
                self.conveyor_gate.disarm(error)
        with self._conveyor_transition:
            if not self.conveyor_gate.enabled:
                return
            self.conveyor_gate.disarm(error)
            self._suspend_conveyor()

    def _conveyor_step(self):
        with self._conveyor_transition:
            gate = self.conveyor_gate
            if not gate.enabled:
                return
            event = gate.tick()
            if event in ('pause', 'resume'):
                self._suspend_conveyor()
                self.logger.info('Conveyor %s (%s/5 visible)', event, gate.visible)
            # An in-flight request finishes with control disabled. Drain its result, then
            # clear observations and actions under the same lock used by inference.
            # Non-blocking acquisition keeps manual Stop and the freshness watchdog responsive.
            if self._conveyor_dirty:
                if not self._inference_execution_lock.acquire(blocking=False):
                    return
                try:
                    self.realtime_data_manager.clear()
                    self._clear_raw_observe_queue()
                    self._conveyor_dirty = False
                finally:
                    self._inference_execution_lock.release()
            if not gate.authorized or gate.phase != 'resuming':
                return
            if not self._conveyor_primed:
                self.start_inference()
                self._conveyor_primed = True
                return
            # Wait for a complete newly fitted chunk, not just a response or raw action.
            with self.realtime_data_manager.action_lock:
                ready = self.realtime_data_manager.action_chunk_fitted is not None
            if ready:
                check = getattr(self.robot, 'check_control_health', None)
                if check:
                    check()
                self._start_control_direct(new_task=False)
                with gate.lock:
                    if gate.authorized:
                        gate.phase = 'running'
                self.logger.info('Conveyor resumed using a fresh action chunk')

    def _conveyor_loop(self):
        while not self._conveyor_shutdown.wait(0.05):
            try:
                self._conveyor_step()
            except Exception as exc:
                self.logger.exception('Conveyor control stopped')
                self._cancel_conveyor(str(exc))
