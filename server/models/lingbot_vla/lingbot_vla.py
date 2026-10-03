"""In-process LingBot adapter for package_a2d observations and absolute actions."""

import importlib
import json
import logging
from pathlib import Path
import sys

import numpy as np
import yaml


class ModelVLA:
    POLICY_CLASSES = {
        25: ('deploy.lingbot_vla_policy_chunk25', 'LingbotVlaChunk25Server'),
        50: ('deploy.lingbot_vla_policy', 'LingbotVLAServer'),
    }
    CAMERA_KEYS = {
        'cam.head': 'observation.images.cam_high_rgb',
        'cam.hand_left': 'observation.images.cam_left_wrist_rgb',
        'cam.hand_right': 'observation.images.cam_right_wrist_rgb',
    }

    def __init__(self, config):
        self.cfg = config
        self.chunk_size = config['chunk_size']
        if type(self.chunk_size) is not int or self.chunk_size not in self.POLICY_CLASSES:
            raise ValueError('LingBot chunk_size must be explicitly set to 25 or 50')
        steps = config['num_denoising_step']
        if type(steps) is not int or steps <= 0:
            raise ValueError('num_denoising_step must be a positive integer')
        for key in ('repo_path', 'model_path', 'norm_path'):
            if not config[key]:
                raise ValueError(f'LingBot requires an explicit {key}')

        repo_path = Path(config['repo_path']).expanduser().resolve()
        model_path = Path(config['model_path']).expanduser().resolve()
        norm_path = Path(config['norm_path']).expanduser().resolve()
        self._check_checkpoint(model_path, norm_path)

        module_name, class_name = self.POLICY_CLASSES[self.chunk_size]
        module_path = repo_path.joinpath(*module_name.split('.')).with_suffix('.py')
        if not module_path.is_file():
            raise FileNotFoundError(module_path)
        sys.path.insert(0, str(repo_path))
        module = importlib.import_module(module_name)
        if Path(module.__file__).resolve() != module_path:
            raise ImportError(f'{module_name} was imported outside repo_path: {module.__file__}')

        logging.getLogger(__name__).info(
            'LingBot %s: model=%s norm=%s chunk_size=%s denoising_steps=%s',
            class_name, model_path, norm_path, self.chunk_size, steps,
        )
        self.policy = getattr(module, class_name)(
            path_to_pi_model=str(model_path),
            robot_norm_path=str(norm_path),
            use_length=self.chunk_size,
            num_denoising_step=steps,
            use_compile=False,
            rtc_mode='off',
        )
        self.policy.reset('package_a2d')
        if (self.policy.config.chunk_size != self.chunk_size
                or self.policy.vla.feature_transform.chunk_size != self.chunk_size):
            raise ValueError('Loaded LingBot policy/FeatureTransform has the wrong chunk_size')

    def _check_checkpoint(self, model_path, norm_path):
        """Reject mismatched training horizons and per-timestep arm statistics before loading."""
        with (model_path / 'lingbotvla_cli.yaml').open() as f:
            training = yaml.safe_load(f)
        if training['train']['chunk_size'] != self.chunk_size:
            raise ValueError('chunk_size does not match checkpoint train.chunk_size')
        if training['data']['data_name'] != 'package_a2d':
            raise ValueError('LingBot adapter requires a package_a2d checkpoint')
        with (model_path / 'config.json').open() as f:
            saved_config = json.load(f)
        saved_chunk = saved_config.get('chunk_size', self.chunk_size)
        # The existing chunk25 class fixes the known stale JSON value before reset().
        if saved_chunk != self.chunk_size and (self.chunk_size, saved_chunk) != (25, 50):
            raise ValueError('config.json chunk_size is incompatible with the checkpoint')
        with norm_path.open() as f:
            arm_stats = json.load(f)['norm_stats']['action.arm.position']
        for key in ('mean', 'std', 'min', 'max', 'q01', 'q99'):
            if np.shape(arm_stats[key]) != (self.chunk_size, 14):
                raise ValueError(f'Arm normalization {key} must have shape ({self.chunk_size}, 14)')

    def infer(self, sequence):
        if len(sequence) != 1:
            raise ValueError('LingBot expects one observation, without history frames')
        data = sequence[0]
        obs = data['obs']
        state = np.asarray(obs['state'])
        # Open-RAIL order: left arm, right arm, grippers, then optional head/waist.
        if state.shape not in ((16,), (20,)) or not np.isfinite(state[:16]).all():
            raise ValueError('state must be a 16- or 20-vector with finite model inputs')
        language = obs['language']
        if isinstance(language, str) or len(language) != 1 or not isinstance(language[0], str):
            raise ValueError('language must contain one task string')
        observation = {
            'observation.state': np.array(state[:16], dtype=np.float32, copy=True),
            'task': language[0],
        }
        for source, target in self.CAMERA_KEYS.items():
            frame = np.asarray(obs[source])
            if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
                raise ValueError(f'{source} must be an HxWx3 RGB uint8 image')
            # LingBot preprocessing mutates its input; preserve the caller's observations.
            observation[target] = frame.copy()

        response = self.policy.infer(observation)
        actions = np.array(response['action'], dtype=np.float32, copy=True)
        if actions.shape != (self.chunk_size, 16) or not np.isfinite(actions).all():
            raise ValueError(f'LingBot actions must be finite with shape ({self.chunk_size}, 16)')
        # FeatureTransform already restored absolute joint targets; do not add state again.
        return {
            'type': 'vla_action',
            'pred_action': actions,
            'ref_timestamp': data['ref_timestamp'],
            'loc_timestamp': data['loc_timestamp'],
            'ext': {},
        }
