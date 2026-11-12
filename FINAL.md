下面命令切换机器人模式并尝试启动通信桥（forwarder）：

```bash
cd /home/bjtc/Sophix/g1-open-rail
hardware/g1/g1_enter_copilot.sh --execute --confirm SWITCH_FROM_VR_TO_COPILOT
```

如果没有forwarder，在单独终端运行并保持打开：

```bash
cd /home/bjtc/Sophix/g1-open-rail
hardware/g1/ros_env_wrapper.sh start
```

模型一：lingboV2 速度0.8

  cd /home/bjtc/Sophix/g1-open-rail

  scripts/run_lingbot_v2_server.sh \
    --model_path /home/bjtc/Sophix/ORI-lingbot-vlaV2/trainedmodel/11-2-data-23to30/hf_ckpt \
    --norm_path /home/bjtc/Sophix/ORI-lingbot-vlaV2/trainedmodel/11-2-data-23to30/norm.json \
    --chunk_size 50 \
    --num_denoising_step 10


模型二：longbo V1 23-29 mask 不好 需要调低base
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_server.sh \
  --model_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/Cmet/10-30-data23to29-mask-uppick/hf_ckpt \
  --norm_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/Cmet/10-30-data23to29-mask-uppick/norm.json \
  --chunk_size 50 --num_denoising_step 10 \
  --image_profile original \
  --image-mask-enabled \
  --image-mask-path /home/bjtc/Sophix/ORI-lingbot-vla/mask/data-1023-1028-table-conveyor-v1/table_conveyor_mask.png \
  --image-mask-camera observation.images.cam_high_rgb

模型三： 需要调整base
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_server.sh \
  --model_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/10-18-cut0922/6whf_ckpt \
  --norm_path /home/bjtc/Sophix/ORI-lingbot-vla/trained-model/10-18-cut0922/norm.json \
  --chunk_size 50 \
  --num_denoising_step 10


启动客户端
cd /home/bjtc/Sophix/g1-open-rail
scripts/run_lingbot_ori_g1_client.sh