import importlib

import numpy as np
import pytest

from server.models.lingbot_image_profile import ImageProfile


@pytest.mark.parametrize('camera', ['cam.head', 'cam.hand_left', 'cam.hand_right'])
def test_original_preserves_pixels_without_aliasing(camera):
    frame = np.random.default_rng(1).integers(0, 256, (30, 40, 3), dtype=np.uint8)
    result = ImageProfile().apply(camera, frame)
    np.testing.assert_array_equal(result, frame)
    assert not np.shares_memory(frame, result)


@pytest.mark.parametrize('camera,width,x', [('cam.head', 768, 200), ('cam.hand_left', 848, 184)])
def test_roi_excludes_surroundings_and_keeps_rgb(camera, width, x):
    frame = np.full((480, width, 3), 255, dtype=np.uint8)
    frame[:, x:x+480] = [15, 80, 160]
    before = frame.copy()
    result = ImageProfile('crop_1016').apply(camera, frame)
    assert result.shape == (224, 224, 3)
    np.testing.assert_array_equal(result, np.broadcast_to([15, 80, 160], result.shape))
    np.testing.assert_array_equal(frame, before)


def test_live_head_uses_training_coordinate_system():
    # Source ROI is x=200/0.6..680/0.6; center stays inside after scaling.
    frame = np.zeros((800, 1280, 3), dtype=np.uint8)
    frame[:, 400:1000] = [20, 60, 200]
    result = ImageProfile('crop_1016').apply('cam.head', frame)
    np.testing.assert_array_equal(result[112,112], [20, 60, 200])
    np.testing.assert_array_equal(result[112,0], [0, 0, 0])
    np.testing.assert_array_equal(result[112,-1], [0, 0, 0])


def test_right_wrist_unchanged():
    frame = np.random.default_rng(2).integers(0, 256, (480,848,3), dtype=np.uint8)
    np.testing.assert_array_equal(ImageProfile('crop_1016').apply('cam.hand_right', frame), frame)


@pytest.mark.parametrize('shape', [(224,224,3), (720,1280,3), (480,848,3)])
def test_wrong_or_already_cropped_head_rejected(shape):
    with pytest.raises(ValueError, match='unsupported'):
        ImageProfile('crop_1016').apply('cam.head', np.zeros(shape, dtype=np.uint8))


def test_invalid_profile_rejected():
    with pytest.raises(ValueError, match='Unknown image_profile'):
        ImageProfile('typo')


@pytest.mark.parametrize('kind', ['ori', 'newarti'])
def test_adapter_passes_cropped_frames_to_policy(kind):
    cls = importlib.import_module(f'server.models.lingbot_{kind}').ModelVLA
    model = cls.__new__(cls)
    model.image_profile = ImageProfile('crop_1016')
    captured = {}
    class Policy:
        def infer(self, observation):
            captured.update(observation)
            return {'action': np.zeros((50,16))}
    model.policy = Policy()
    obs = {'state': np.arange(16), 'language': ['test'],
           'cam.head': np.zeros((800,1280,3), dtype=np.uint8),
           'cam.hand_left': np.zeros((480,848,3), dtype=np.uint8),
           'cam.hand_right': np.zeros((480,848,3), dtype=np.uint8)}
    result = model.infer([{'obs': obs, 'ref_timestamp': 1, 'loc_timestamp': 2}])
    for source, target in cls.CAMERA_KEYS.items():
        assert captured[target].shape == ((480,848,3) if source == 'cam.hand_right' else (224,224,3))
    np.testing.assert_array_equal(captured['observation.state'], obs['state'])
    assert result['pred_action'].shape == (50,16)
    assert obs['cam.head'].shape == (800,1280,3)


@pytest.mark.parametrize('kind', ['lingbot_ori', 'lingbot_newarti'])
def test_cli_selects_profile(kind, monkeypatch):
    import run_server
    from conf.server_conf import get_vla_server_config
    monkeypatch.setattr('sys.argv', ['run_server.py', '--model_type', kind, '--image_profile', 'crop_1016'])
    config = run_server.override_config_with_args(get_vla_server_config(), run_server.parse_args())
    assert config.models[kind].image_profile == 'crop_1016'


def test_cropped_preview_preserves_inference_transport():
    import cv2
    from client.core.vla_client import VLAClient
    client = VLAClient.__new__(VLAClient)
    client.preview_image_profile = ImageProfile('crop_1016')
    frames = {}
    for key, shape in [('cam.head', (800,1280,3)), ('cam.hand_left', (480,848,3)),
                       ('cam.hand_right', (480,848,3))]:
        frame = np.zeros(shape, dtype=np.uint8)
        frame[:] = [20,80,170]  # BGR
        _, encoded = cv2.imencode('.jpg', frame)
        frames[key] = memoryview(encoded)
    before = {k: bytes(v) for k,v in frames.items()}
    result = client._preview_images(frames)
    for key in frames:
        assert bytes(frames[key]) == before[key]
        decoded = cv2.imdecode(np.frombuffer(result[key],np.uint8),cv2.IMREAD_COLOR)
        assert decoded.shape == ((480,848,3) if key=='cam.hand_right' else (224,224,3))
        np.testing.assert_allclose(decoded[100,100], [20,80,170], atol=3)
    assert result['cam.hand_right'] is frames['cam.hand_right']
    client.preview_image_profile = ImageProfile('original')
    assert client._preview_images(frames) is frames
