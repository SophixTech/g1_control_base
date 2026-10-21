"""G1 adapter for the native Qwen3-VL LingBot V2 policy."""

import copy
import importlib
from pathlib import Path
import sys

import numpy as np
import yaml

from server.models.lingbot_image_profile import ImageProfile


class ModelVLA:
    MODULE = 'deploy.lingbot_vla_v2_policy'
    CAMERA_KEYS = {
        'cam.head': 'observation.images.cam_high_rgb',
        'cam.hand_left': 'observation.images.cam_left_wrist_rgb',
        'cam.hand_right': 'observation.images.cam_right_wrist_rgb',
    }

    @staticmethod
    def _check_import_origins(repo):
        for name, module in list(sys.modules.items()):
            if not (name in ('deploy', 'lingbotvla') or name.startswith(('deploy.', 'lingbotvla.'))):
                continue
            origins = list(getattr(module, '__path__', []))
            if getattr(module, '__file__', None):
                origins.append(module.__file__)
            for origin in origins:
                if not Path(origin).resolve().is_relative_to(repo):
                    raise ImportError(f'V2 import collision: {name} comes from {origin}; start a fresh server')

    def __init__(self, config):
        self.cfg = config
        self.chunk_size = config['chunk_size']
        self.image_profile = ImageProfile(config.get('image_profile', 'original'))
        for key in ('repo_path', 'model_path', 'norm_path'):
            if not config.get(key):
                raise ValueError(f'V2 requires an explicit {key}')
        repo, checkpoint, norm = (Path(config[k]).expanduser().resolve()
                                  for k in ('repo_path', 'model_path', 'norm_path'))
        # Native V2 reads the run YAML three levels above hf_ckpt.
        training_path = checkpoint.parent.parent.parent / 'lingbotvla_cli.yaml'
        training = yaml.safe_load(training_path.read_text())
        horizon = training['train'].get('chunk_size', training['model'].get('chunk_size', 50))
        if self.chunk_size != horizon:
            raise ValueError(f'V2 chunk_size={self.chunk_size} differs from training horizon={horizon}')
        if not norm.is_file():
            raise FileNotFoundError(norm)
        if config['num_denoising_step'] <= 0:
            raise ValueError('num_denoising_step must be positive')
        robot_file = Path(__file__).with_name('package_a2d.yaml')
        self._check_import_origins(repo)
        sys.path.insert(0, str(repo))
        module = importlib.import_module(self.MODULE)
        self._check_import_origins(repo)

        class V2Policy(module.LingbotVLAv2Server):
            def reset(self, robo_name, path_to_pi_model=None):
                if robo_name != 'package_a2d' or path_to_pi_model is not None:
                    raise ValueError('Start a new V2 server to change checkpoint or robot')
                self.global_step = 0
                self.last_action_chunk = None
                self.last_normalized_action_chunk = None
                self.robot_config = yaml.safe_load(robot_file.read_text())
                data_config = copy.copy(self.data_config)
                # YAML may contain mappings; native FeatureTransform parses strings.
                for name in ('joints', 'norm_type'):
                    values = getattr(data_config, name, None)
                    if values is not None:
                        setattr(data_config, name, [repr(v) if isinstance(v, dict) else v for v in values])
                self.vla.feature_transform = module.FeatureTransform(
                    str(robot_file), data_config, self.config, self.processor,
                    chunk_size=self.config.chunk_size, norm_stats_path=self.robot_norm_path,
                )
                self.action_key = self.vla.feature_transform.org_features['actions']

        self.policy = V2Policy(
            path_to_pi_model=str(checkpoint), robot_norm_path=str(norm),
            use_length=self.chunk_size, chunk_ret=True, use_compile=False,
        )
        # Native sample_actions reads model.config.num_steps at inference time.
        self.policy.config.num_steps = config['num_denoising_step']
        self.policy.vla.model.config.num_steps = config['num_denoising_step']
        self.policy.reset('package_a2d')
        if self.policy.config.chunk_size != self.chunk_size:
            raise ValueError('Loaded V2 action horizon differs from the requested chunk_size')

    def infer(self, sequence):
        if len(sequence) != 1:
            raise ValueError('V2 expects one current observation')
        data = sequence[0]
        obs = data['obs']
        state = np.asarray(obs['state'])
        if state.shape not in ((16,), (20,)) or not np.isfinite(state[:16]).all():
            raise ValueError('V2 state must contain 16 finite arm/gripper values')
        language = obs['language']
        if isinstance(language, str) or len(language) != 1 or not isinstance(language[0], str):
            raise ValueError('V2 language must contain one task string')
        observation = {'observation.state': np.array(state[:16], dtype=np.float32, copy=True),
                       'task': language[0]}
        for source, target in self.CAMERA_KEYS.items():
            observation[target] = self.image_profile.apply(source, obs[source])
        response = self.policy.infer(observation)
        # Native unapply maps internal joint slots back to raw 16-D absolute targets.
        # Do not slice the first 16 values from the internal 55-D action tensor.
        actions = np.array(response['action'], dtype=np.float32, copy=True)
        if actions.shape != (self.chunk_size, 16) or not np.isfinite(actions).all():
            raise ValueError(f'V2 actions must be finite with shape ({self.chunk_size}, 16)')
        return dict(type='vla_action', pred_action=actions,
                    ref_timestamp=data['ref_timestamp'], loc_timestamp=data['loc_timestamp'], ext={})
