"""Opt-in, bounded asynchronous diagnostics; never a motion command source."""

import json
import logging
import queue
import threading
import time
from pathlib import Path


class JointTrace:
    def __init__(self, directory, stream, joint, queue_size=4096):
        if not 0 <= int(joint) < 14:
            raise ValueError('Trace joint must be 0..13 (left 0..6, right 7..13)')
        self.joint = int(joint)
        self.directory = str(Path(directory).resolve())
        self.path = Path(self.directory) / f'{stream}.jsonl'
        self._file = self.path.open('x', encoding='utf-8')
        self._queue = queue.Queue(maxsize=queue_size)
        self._closing = threading.Event()
        self.dropped = 0
        self.error = None
        self._thread = threading.Thread(target=self._write, daemon=True, name=f'trace-{stream}')
        self._thread.start()
        self.record('stream_start', schema_version=1, joint=self.joint, stream=stream,
                    clock='PC perf_counter_ns; device stamps are a separate clock')

    def record(self, event, **fields):
        if self._closing.is_set() or self.error:
            self.dropped += 1
            return False
        row = dict(event=event, mono_ns=time.perf_counter_ns(), wall_ns=time.time_ns(), **fields)
        try:
            self._queue.put_nowait(row)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def _write(self):
        last_flush = time.monotonic()
        try:
            while not self._closing.is_set() or not self._queue.empty():
                try:
                    row = self._queue.get(timeout=0.1)
                except queue.Empty:
                    self._file.flush()
                    continue
                self._file.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                if time.monotonic() - last_flush >= 0.25:
                    self._file.flush()
                    last_flush = time.monotonic()
            self._file.write(json.dumps(dict(event='stream_end', mono_ns=time.perf_counter_ns(),
                                            dropped=self.dropped)) + '\n')
            self._file.flush()
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
            logging.getLogger(__name__).error('Joint trace failed (%s): %s', self.path, self.error)
        finally:
            self._file.close()

    def close(self):
        self._closing.set()
        self._thread.join(timeout=3)
        if self._thread.is_alive():
            logging.getLogger(__name__).warning('Joint trace flush incomplete: %s', self.path)

    @property
    def status(self):
        return dict(directory=self.directory, joint=self.joint, dropped=self.dropped, error=self.error)
