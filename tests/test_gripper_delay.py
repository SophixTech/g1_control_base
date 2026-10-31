import numpy as np
from client.core.gripper_delay import GripperDelay


def test_delay_spans_chunks_and_holds_initial_target():
    delay = GripperDelay()
    # Chunk A is open; chunk B starts closing before the delay has elapsed.
    assert delay.sample([0, 0], 0, .5) is None
    assert delay.sample([0, 1], .2, .5) is None
    np.testing.assert_array_equal(delay.sample([1, 1], .5, .5), [0, 0])
    np.testing.assert_array_equal(delay.sample([1, 1], .7, .5), [0, 1])
    np.testing.assert_array_equal(delay.sample([1, 1], 1, .5), [1, 1])


def test_reset_and_delay_change_discard_pending_commands():
    delay = GripperDelay()
    delay.sample([1, 1], 0, .5)
    delay.clear()
    assert delay.sample([0, 0], 1, .5) is None
    np.testing.assert_array_equal(delay.sample([0, 0], 1.5, .5), [0, 0])
    assert delay.sample([1, 1], 2, 1) is None
    np.testing.assert_array_equal(delay.sample([0, 0], 2.1, 0), [0, 0])
