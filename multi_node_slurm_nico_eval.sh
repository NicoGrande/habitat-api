#!/bin/bash
#SBATCH --job-name=pointnav-via-ib-nico
#SBATCH --output=logs_eval_baseline_no_sensor.out
#SBATCH --error=logs_eval_baseline_no_sensor.err
#SBATCH --gres gpu:1
#SBATCH --nodes 1
#SBATCH --ntasks-per-node 1
#SBATCH --partition=long

echo "Using setup for Nico"
. ${HOME}/miniconda3/etc/profile.d/conda.sh
conda deactivate
conda activate habitat
export GLOG_minloglevel=2
export MAGNUM_LOG=quiet
export MASTER_ADDR=$(srun --ntasks=1 hostname 2>&1 | tail -n1)
set -x
srun python -u -m habitat_baselines.run \
    --exp-config habitat_baselines/config/pointnav/ddppo_pointnav.yaml \
    --run-type eval \
    RL.PPO.start_beta 1e1 \
    RL.PPO.decay_start_step 1e8 \
    RL.PPO.beta_decay_steps 1e8 \
    TENSORBOARD_DIR tb/beta_1e1_100M_100M_regular_no_sensor_v1_eval_test \
    EVAL_CKPT_PATH_DIR data/checkpoints/beta_1e1_100M_100M_baseline_train_noisy_test_v1 \
    CHECKPOINT_FOLDER data/checkpoints/beta_1e1_100M_100M_regular_no_sensor_v1_eval_test \
    NUM_PROCESSES 3