"""Synchronous single-frame scaling through FFmpeg libswscale (PyAV)."""
import numpy as np


def resize_head_rgb(frame):
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError('Head frame must be HxWx3 RGB uint8')
    height, width = frame.shape[:2]
    if width * 480 != height * 768:
        raise ValueError(f'Head original resolution must have 16:10 aspect ratio, got {width}x{height}')
    if (height, width) == (480, 768):
        return frame
    import av
    source = av.VideoFrame.from_ndarray(frame, format='rgb24')
    scaled = source.reformat(width=768, height=480, format='rgb24', interpolation='LANCZOS')
    return scaled.to_ndarray(format='rgb24')
