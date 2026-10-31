"""Delay the executed gripper stream across prediction chunk boundaries."""
from collections import deque
import math
import numpy as np


class GripperDelay:
    def __init__(self):
        self.clear()

    def clear(self):
        self.pending = deque()
        self.delay = None
        self.output = None

    def sample(self, values, now, delay):
        delay = float(delay)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError('gripper delay must be finite and nonnegative')
        if self.delay != delay:
            self.clear()
            self.delay = delay
        if delay == 0:
            return np.array(values, copy=True)
        self.pending.append((now + delay, np.array(values, copy=True)))
        while self.pending and self.pending[0][0] <= now:
            _, self.output = self.pending.popleft()
        # None means retain the hardware's previous target during warm-up.
        return None if self.output is None else self.output.copy()
