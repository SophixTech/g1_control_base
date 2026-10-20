"""Optional camera preprocessing shared by the ORI and NEWARTI adapters."""

import logging

import numpy as np
from PIL import Image


class ImageProfile:
    PROFILES = ('original', 'crop_1016')

    def __init__(self, name='original'):
        if name not in self.PROFILES:
            raise ValueError(f'Unknown image_profile: {name!r}; expected {self.PROFILES}')
        self.name = name
        self._logged = set()
        logging.getLogger(__name__).info('LingBot image_profile=%s', name)

    def apply(self, camera, frame):
        frame = np.asarray(frame)
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError(f'{camera} must be HxWx3 RGB uint8')
        size = (frame.shape[1], frame.shape[0])
        roi = None
        if self.name == 'original':
            result = frame.copy()
        else:
            allowed = {'cam.head': ((1280, 800), (768, 480)),
                       'cam.hand_left': ((848, 480),),
                       'cam.hand_right': ((848, 480),)}
            if camera not in allowed or size not in allowed[camera]:
                raise ValueError(f'crop_1016: unsupported {camera} size {size}; '
                                 f'expected {allowed.get(camera)} (width, height)')
            if camera == 'cam.hand_right':
                result = frame.copy()
            else:
                image = Image.fromarray(frame)
                if camera == 'cam.head' and size == (1280, 800):
                    image = image.resize((768, 480), Image.Resampling.LANCZOS)
                x = 200 if camera == 'cam.head' else 184
                roi = (x, 0, 480, 480)
                # Match training geometry. PIL and FFmpeg codecs/resamplers
                # are not bit-identical; no video recompression at inference.
                image = image.crop((x, 0, x + 480, 480))
                result = np.array(image.resize((224, 224), Image.Resampling.BICUBIC), copy=True)
        signature = (camera, size)
        if signature not in self._logged:
            logging.getLogger(__name__).info(
                'image_profile=%s camera=%s source=%s roi=%s output=%s',
                self.name, camera, size, roi, (result.shape[1], result.shape[0]))
            self._logged.add(signature)
        return result
