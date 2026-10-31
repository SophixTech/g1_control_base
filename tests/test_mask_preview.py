import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
import pytest
from client.core.mask_preview import HeadMaskPreview


def test_mask_preserves_original_and_matches_ori_resize(tmp_path):
    keep = np.zeros((480, 768), dtype=np.uint8)
    keep[:, :384] = 255
    path = tmp_path / 'mask.png'
    Image.fromarray(keep).save(path)
    frame = np.random.default_rng(1).integers(0, 256, (800, 1280, 3), dtype=np.uint8)
    original = frame.copy()
    out = HeadMaskPreview(True, str(path)).apply(frame)
    expected = np.array(Image.fromarray(frame).resize((768, 480), Image.Resampling.LANCZOS))
    expected[:, 384:] = 0
    np.testing.assert_array_equal(out, expected)
    np.testing.assert_array_equal(frame, original)
    assert HeadMaskPreview(False, '/missing').apply(frame) is frame
    with pytest.raises(ValueError, match='does not match'):
        HeadMaskPreview(True, str(path)).apply(np.zeros((224, 224, 3), np.uint8))


def test_preview_only_changes_head_display_bytes(tmp_path):
    cv2 = pytest.importorskip('cv2')
    path = tmp_path / 'mask.png'
    keep = np.ones((480, 768), np.uint8) * 255
    keep[:, :384] = 0
    Image.fromarray(keep).save(path)
    source = Path(__file__).resolve().parents[1] / 'client/core/vla_client.py'
    cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_preview_images')
    ns = dict(np=np, cv2=cv2)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), ns)
    obj = SimpleNamespace(preview_image_profile=None, head_mask_preview=HeadMaskPreview(True, str(path)))
    _, data = cv2.imencode('.jpg', np.full((800, 1280, 3), 200, np.uint8))
    images = {'cam.head': data.tobytes(), 'cam.hand_left': data.tobytes(), 'cam.hand_right': data.tobytes()}
    original = dict(images)
    result = ns['_preview_images'](obj, images)
    assert images == original
    assert result['cam.hand_left'] is images['cam.hand_left']
    assert result['cam.hand_right'] is images['cam.hand_right']
    decoded = cv2.imdecode(np.frombuffer(result['cam.head'], np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (480, 768, 3)
    assert decoded[:, :380].max() == 0
    obj.head_mask_preview = HeadMaskPreview(False)
    assert ns['_preview_images'](obj, images) is images
