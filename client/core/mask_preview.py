"""Display-only head mask, matching ORI's pre-mask resize."""
from pathlib import Path
import numpy as np
from PIL import Image


class HeadMaskPreview:
    def __init__(self, enabled=False, path=''):
        self.enabled = enabled
        self.keep = None
        if enabled:
            if not path:
                raise ValueError('Head mask preview requires a mask PNG path')
            with Image.open(Path(path).expanduser()) as image:
                self.keep = np.array(image.convert('L')) > 0

    def apply(self, rgb):
        if not self.enabled:
            return rgb
        if rgb.shape[:2] == (800, 1280) and self.keep.shape == (480, 768):
            rgb = np.array(Image.fromarray(rgb).resize((768, 480), Image.Resampling.LANCZOS))
        if rgb.shape[:2] != self.keep.shape:
            raise ValueError(f'Head preview shape {rgb.shape[:2]} does not match mask {self.keep.shape}')
        return np.where(self.keep[..., None], rgb, np.zeros((), dtype=rgb.dtype))
