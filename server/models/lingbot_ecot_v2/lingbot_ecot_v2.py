"""Independent predicted-label K/V ECOT V2 adapter. Run in a fresh model-server process."""

import importlib
import json
import logging
from pathlib import Path
import struct
import sys

import numpy as np
import yaml

from server.models.lingbot_image_profile import ImageProfile


class ModelVLA:
    CAMERA_KEYS = {
        'cam.head': 'observation.images.cam_high_rgb',
        'cam.hand_left': 'observation.images.cam_left_wrist_rgb',
        'cam.hand_right': 'observation.images.cam_right_wrist_rgb',
    }
    MODULE = 'deploy.lingbot_vla_policy'
    MODEL_MODULE = 'lingbotvla.models.vla.pi0.modeling_lingbot_vla'

    @staticmethod
    def _check_import_origins(repo):
        # sys.path cannot fix an already imported package from another checkout.
        for name, module in list(sys.modules.items()):
            if not (name in ('deploy', 'lingbotvla') or name.startswith(('deploy.', 'lingbotvla.'))):
                continue
            origins = list(getattr(module, '__path__', []))
            if getattr(module, '__file__', None):
                origins.append(module.__file__)
            for origin in origins:
                if not Path(origin).resolve().is_relative_to(repo):
                    raise ImportError(f'ECOT V2 import collision: {name} comes from {origin}; start a fresh process with {repo}')

    @classmethod
    def validate_artifacts(cls, config):
        """Read configs and safetensors headers only; no torch, CUDA or sockets."""
        for key in ('repo_path', 'model_path', 'norm_path'):
            if not config.get(key):
                raise ValueError(f'ECOT V2 requires an explicit {key}')
        if type(config['chunk_size']) is not int or config['chunk_size'] != 50:
            raise ValueError('This ECOT V2 adapter supports chunk_size=50 only')
        steps = config['num_denoising_step']
        if type(steps) is not int or steps <= 0:
            raise ValueError('num_denoising_step must be a positive integer')
        repo, checkpoint, norm = (Path(config[k]).expanduser().resolve()
                                  for k in ('repo_path', 'model_path', 'norm_path'))
        for module in (cls.MODULE, cls.MODEL_MODULE):
            path = repo.joinpath(*module.split('.')).with_suffix('.py')
            if not path.is_file():
                raise FileNotFoundError(path)
        training = yaml.safe_load((checkpoint / 'lingbotvla_cli.yaml').read_text())
        train, data = training['train'], training['data']
        if train.get('ecot_aux_supervision') is not True:
            raise ValueError('Checkpoint must enable train.ecot_aux_supervision')
        if train.get('chunk_size') != 50 or data.get('data_name') != 'package_a2d':
            raise ValueError('ECOT V2 checkpoint must use package_a2d and train.chunk_size=50')
        saved = json.loads((checkpoint / 'config.json').read_text())
        if saved.get('chunk_size') != 50 or saved.get('n_action_steps') != 50:
            raise ValueError('ECOT V2 config.json must specify a 50-step horizon')
        # The native loader prefers config.json and fills missing keys from YAML.
        effective = {**training.get('model', {}), **train, **saved}
        if effective.get('ecot_aux_supervision') is not True or effective.get('ecot_label_kv_conditioning') is not True:
            raise ValueError('ECOT V2 requires ecot_aux_supervision and ecot_label_kv_conditioning=true')
        if effective.get('ecot_action_conditioning', False):
            raise ValueError('ECOT V2 requires ecot_action_conditioning=false')
        if data.get('norm_type') not in ('meanstd', 'bounds_99', 'minmax'):
            raise ValueError('ECOT V2 requires a supported explicit training norm_type')
        robot_root = Path(data.get('robot_config_root', 'configs/robot_configs'))
        robot_root = (repo / robot_root).resolve() if not robot_root.is_absolute() else robot_root.resolve()
        if not robot_root.is_relative_to(repo):
            raise ValueError('ECOT V2 robot_config_root must belong to the ECOT V2 checkout')
        robot_file = robot_root / 'package_a2d.yaml'
        layout = yaml.safe_load(robot_file.read_text())
        action_groups = {key: value for group in layout['actions'] for key, value in group.items()}
        arm = action_groups['action.arm.position']
        effector = action_groups['action.effector.position']
        if arm.get('subtract_state') is not True or effector.get('subtract_state', False):
            raise ValueError('ECOT V2 expects delta arm actions and absolute gripper actions before unapply')
        stats = json.loads(norm.read_text())['norm_stats']
        for feature, shape in (('action.arm.position', (50, 14)),
                               ('action.effector.position', (2,)),
                               ('observation.state.arm.position', (14,)),
                               ('observation.state.effector.position', (2,))):
            for key in ('mean', 'std', 'min', 'max', 'q01', 'q99'):
                values = np.asarray(stats[feature][key], dtype=float)
                if values.shape != shape or not np.isfinite(values).all():
                    raise ValueError(f'Invalid ECOT V2 normalization {feature}.{key}; expected finite {shape}')
        headers = {}
        shards = sorted(checkpoint.glob('*.safetensors'))
        if not shards:
            raise ValueError('ECOT V2 checkpoint contains no safetensors weights')
        for shard in shards:
            with shard.open('rb') as stream:
                size = struct.unpack('<Q', stream.read(8))[0]
                if size > 64 * 1024 * 1024 or size > shard.stat().st_size - 8:
                    raise ValueError(f'Invalid safetensors header length: {shard}')
                header = json.loads(stream.read(size))
            for key, value in header.items():
                if key == '__metadata__':
                    continue
                if key in headers:
                    raise ValueError(f'Duplicate checkpoint parameter: {key}')
                headers[key] = value
        heads = [('subtask', 4), ('bbox', 4), ('label', 2)]
        if effective.get('ecot_visibility', False):
            heads.append(('visibility', 1))
        for head, outputs in heads:
            prefix = f'model.ecot_{head}_head'
            for layer in ('0.weight', '0.bias', '1.weight', '1.bias'):
                if f'{prefix}.{layer}' not in headers:
                    raise ValueError(f'Missing ECOT V2 weight: {prefix}.{layer}')
            if headers[f'{prefix}.1.weight']['shape'][0] != outputs:
                raise ValueError(f'Wrong ECOT V2 output shape: {prefix}')
        prefix = 'model.ecot_label_kv_projector.'
        for layer in ('label_encoder.0', 'label_encoder.2'):
            for suffix in ('weight', 'bias'):
                if prefix + layer + '.' + suffix not in headers:
                    raise ValueError(f'Missing ECOT V2 label K/V weight: {layer}.{suffix}')
        indices = sorted({int(key[len(prefix + 'layer_kv_proj.'):].split('.')[0])
                          for key in headers if key.startswith(prefix + 'layer_kv_proj.')})
        if not indices or indices != list(range(len(indices))):
            raise ValueError('Missing or non-contiguous ECOT V2 per-layer K/V weights')
        for index in indices:
            for suffix in ('weight', 'bias'):
                if f'{prefix}layer_kv_proj.{index}.{suffix}' not in headers:
                    raise ValueError(f'Missing ECOT V2 layer {index} K/V {suffix}')
        if train.get('use_lora', False):
            if not any('lora_A' in key for key in headers) or not any('lora_B' in key for key in headers):
                raise ValueError('Missing ECOT V2 LoRA weights')
        elif any('lora_' in key for key in headers):
            raise ValueError('LoRA weights disagree with train.use_lora=false')
        return dict(model_type='lingbot_ecot_v2', repo_path=str(repo), model_path=str(checkpoint),
                    norm_path=str(norm), robot_config=str(robot_file), chunk_size=50,
                    ecot_heads=[head for head, _ in heads], label_kv_layers=len(indices),
                    use_lora=bool(train.get('use_lora', False)), norm_type=data['norm_type'],
                    lora_weight_count=sum('lora_' in key for key in headers),
                    validation='metadata and weight headers only; model not instantiated')

    def __init__(self, config):
        self.cfg = config
        self.chunk_size = 50
        self.image_profile = ImageProfile(config.get('image_profile', 'original'))
        artifacts = self.validate_artifacts(config)
        repo = Path(artifacts['repo_path'])
        self._check_import_origins(repo)
        sys.path.insert(0, str(repo))
        module = importlib.import_module(self.MODULE)
        self._check_import_origins(repo)
        model_module = importlib.import_module(self.MODEL_MODULE)
        if Path(module.__file__).resolve() != repo.joinpath(*self.MODULE.split('.')).with_suffix('.py'):
            raise ImportError('ECOT V2 deployment entry was imported from the wrong checkout')
        if Path(model_module.__file__).resolve() != repo.joinpath(*self.MODEL_MODULE.split('.')).with_suffix('.py'):
            raise ImportError('ECOT V2 model was imported from the wrong checkout')
        logging.getLogger(__name__).info('ECOT V2 artifacts: %s; model source=%s', artifacts, model_module.__file__)
        # Native loader optionally rebuilds LoRA, then loads all weights with strict=True.
        self.policy = module.LingbotVLAServer(
            path_to_pi_model=artifacts['model_path'], robot_norm_path=artifacts['norm_path'],
            use_length=50, num_denoising_step=config['num_denoising_step'],
            use_compile=False, rtc_mode='off',
        )
        self.policy.reset('package_a2d')
        if self.policy.config.chunk_size != 50 or self.policy.vla.feature_transform.chunk_size != 50:
            raise ValueError('Loaded ECOT V2 policy/FeatureTransform must have chunk_size=50')
        model = self.policy.vla.model
        if not getattr(model, 'ecot_label_kv_conditioning', False) or not hasattr(model, 'ecot_label_kv_projector'):
            raise ValueError('Loaded policy has no ECOT V2 label K/V conditioning')
        if not getattr(model, 'ecot_aux_supervision', False) or not all(
            hasattr(model, f'ecot_{head}_head') for head in artifacts['ecot_heads']
        ):
            raise ValueError('Loaded policy does not contain required ECOT V2 heads')

    def infer(self, sequence):
        if len(sequence) != 1:
            raise ValueError('ECOT V2 expects one observation without history frames')
        data = sequence[0]
        obs = data['obs']
        state = np.asarray(obs['state'])
        if state.shape not in ((16,), (20,)) or not np.isfinite(state[:16]).all():
            raise ValueError('ECOT V2 state must be a finite 16- or 20-vector')
        language = obs['language']
        if isinstance(language, str) or len(language) != 1 or not isinstance(language[0], str):
            raise ValueError('ECOT V2 language must contain one task string')
        observation = {'observation.state': np.array(state[:16], dtype=np.float32, copy=True),
                       'task': language[0]}
        for source, target in self.CAMERA_KEYS.items():
            observation[target] = self.image_profile.apply(source, obs[source])
        response = self.policy.infer(observation)
        actions = np.array(response['action'], dtype=np.float32, copy=True)
        if actions.shape != (50, 16) or not np.isfinite(actions).all():
            raise ValueError('ECOT V2 actions must be finite with shape (50, 16)')
        # Native FeatureTransform.unapply already restores absolute arm targets.
        # Predicted label probabilities condition native action attention through K/V.
        # No ground-truth labels or frontend subtask completion signals are supplied.
        return dict(type='vla_action', pred_action=actions,
                    ref_timestamp=data['ref_timestamp'], loc_timestamp=data['loc_timestamp'], ext={})
