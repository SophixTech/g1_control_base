"""Optional conveyor interlock: raw BGR ROI detection and a small timed state machine."""
import base64
import threading
import time

import cv2
import numpy as np


DEFAULTS = dict(enabled=False, camera='cam.head', reference_size=[1280, 800], rois=[],
                min_visible=3, stop_delay_s=2.0, resume_stable_s=0.5, detect_hz=10.0,
                frame_timeout_s=0.5, hsv_red_ranges=[[0, 10], [170, 179]],
                saturation_min=100, value_min=60, min_blob_area_px=20)


class ConveyorGate:
    def __init__(self, config=None):
        self.lock = threading.RLock()
        self.config = {**DEFAULTS, **dict(config or {})}
        self.authorized = False
        self.phase = 'disabled' if not self.config['enabled'] else 'stopped'
        self.error = None
        self.last_frame = None
        self.last_check = -float('inf')
        self.visible = 0
        self.points = []
        self.good_since = None
        self.deadline = None
        self.preview = None
        self.revision = 0
        self.validate(require_rois=False)

    @property
    def enabled(self):
        return self.config['enabled']

    def validate(self, require_rois=True):
        c = self.config
        w, h = c['reference_size']
        if w <= 0 or h <= 0 or (len(c['rois']) != 5 and (require_rois or c['rois'])):
            raise ValueError('请先配置 5 个红点 ROI [x, y, width, height]')
        for roi in c['rois']:
            if len(roi) != 4 or not all(type(v) is int for v in roi):
                raise ValueError('ROI 必须包含 4 个有效数值')
            x, y, rw, rh = roi
            if x < 0 or y < 0 or rw <= 0 or rh <= 0 or x+rw > w or y+rh > h:
                raise ValueError('红点 ROI 超出参考图像范围')
        if not all(np.isfinite(c[k]) for k in ('stop_delay_s','resume_stable_s','detect_hz','frame_timeout_s','min_blob_area_px')):
            raise ValueError('检测参数必须是有限数值')
        if not 1 <= c['min_visible'] <= 5 or c['detect_hz'] <= 0 or c['frame_timeout_s'] <= 0:
            raise ValueError('无效的红点检测数量、频率或超时')
        if c['stop_delay_s'] < 0 or c['resume_stable_s'] < 0 or c['min_blob_area_px'] <= 0:
            raise ValueError('延迟、稳定时间和面积阈值无效')

    def arm(self):
        with self.lock:
            self.validate()
            self.authorized = True
            self.phase = 'waiting'
            self.error = None
            self.last_frame = None
            self.good_since = self.deadline = None

    def disarm(self, error=None):
        with self.lock:
            self.authorized = False
            self.error = str(error) if error else None
            self.phase = 'fault' if error else ('stopped' if self.enabled else 'disabled')
            self.good_since = self.deadline = None

    def update(self, frame, source_time=None, now=None):
        now = time.perf_counter() if now is None else now
        with self.lock:
            if not self.enabled or now-self.last_check < 1/self.config['detect_hz']:
                return
            self.last_check = now
            try:
                self.validate()
                if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
                    raise ValueError('未收到有效头部图像')
                h, w = frame.shape[:2]
                rw, rh = self.config['reference_size']
                if abs(w/h-rw/rh) > 0.01:
                    raise ValueError('头部图像宽高比与 ROI 参考图不一致，请重新标定')
                # Detection in reference pixels keeps area thresholds independent of stream resolution.
                if (w, h) != (rw, rh):
                    frame = cv2.resize(frame, (int(rw), int(rh)), interpolation=cv2.INTER_AREA)
                points, tiles = [], []
                for i, (x, y, width, height) in enumerate(self.config['rois']):
                    x, y, width, height = map(int, (x, y, width, height))
                    roi = frame[y:y+height, x:x+width]
                    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
                    for lo, hi in self.config['hsv_red_ranges']:
                        mask |= cv2.inRange(hsv, (lo, self.config['saturation_min'], self.config['value_min']), (hi,255,255))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
                    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
                    area = int(stats[1:, cv2.CC_STAT_AREA].max()) if len(stats)>1 else 0
                    seen = area >= self.config['min_blob_area_px']
                    points.append(dict(visible=bool(seen), area=area))
                    tile = cv2.resize(roi, (128,96))
                    tile = cv2.copyMakeBorder(tile,0,24,0,0,cv2.BORDER_CONSTANT)
                    cv2.putText(tile, f'{i+1}: {area} '+('YES' if seen else 'NO'), (3,112),
                                cv2.FONT_HERSHEY_SIMPLEX,.4,(0,255,0) if seen else (0,0,255),1)
                    tiles.append(tile)
                ok, jpg = cv2.imencode('.jpg', np.hstack(tiles), [cv2.IMWRITE_JPEG_QUALITY,75])
                self.preview = base64.b64encode(jpg).decode('ascii') if ok else None
                self.revision += 1
                self.points = points
                self.visible = sum(p['visible'] for p in points)
                self.last_frame = now if source_time is None else source_time
                if self.phase != 'fault':
                    self.error = None
            except (ValueError, cv2.error) as exc:
                self.error = str(exc)
                self.last_frame = None

    def tick(self, now=None):
        now = time.perf_counter() if now is None else now
        with self.lock:
            if not self.enabled or not self.authorized:
                return None
            fresh = self.last_frame is not None and 0 <= now-self.last_frame <= self.config['frame_timeout_s']
            good = fresh and self.visible >= self.config['min_visible']
            if not good:
                self.good_since = None
            elif self.good_since is None:
                self.good_since = now
            if self.phase in ('running', 'countdown'):
                if not fresh:
                    self.phase = 'waiting'
                    self.deadline = None
                    return 'pause'
                if good:
                    self.phase = 'running'
                    self.deadline = None
                else:
                    if self.deadline is None:
                        self.deadline = now+self.config['stop_delay_s']
                    self.phase = 'countdown'
                    if now >= self.deadline:
                        self.phase = 'waiting'
                        self.deadline = None
                        return 'pause'
            elif self.phase == 'resuming' and not good:
                self.phase = 'waiting'
                return 'pause'
            elif self.phase == 'waiting' and good and now-self.good_since >= self.config['resume_stable_s']:
                self.phase = 'resuming'
                return 'resume'
            return None

    def status(self, include_image=False):
        with self.lock:
            now = time.perf_counter()
            result = dict(enabled=self.enabled, authorized=self.authorized, phase=self.phase,
                          visible=self.visible, points=self.points, error=self.error,
                          remaining_s=max(0,self.deadline-now) if self.deadline is not None else None,
                          frame_age_s=max(0,now-self.last_frame) if self.last_frame is not None else None,
                          revision=self.revision)
            if include_image:
                result['preview_jpeg'] = self.preview
                result['config'] = self.config
            return result
