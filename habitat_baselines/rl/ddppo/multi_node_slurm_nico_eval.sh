#!/bin/bash
#SBATCH --job-name=pointnav-via-ib-nico
#SBATCH --output=logs_eval_noisy_baseline.out
#SBATCH --error=logs_eval_noisy_baseline.err
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
    RL.PPO.start_beta 5e-3 \
    RL.PPO.decay_start_step 1e8 \
    RL.PPO.beta_decay_steps 1e8 \
    RL.PPO.final_beta 5e-3 \
    TENSORBOARD_DIR tb/beta_5e-3_100M_100M_baseline_regular_train_noisy_test_eval \
    EVAL_CKPT_PATH_DIR data/checkpoints/beta_5e-3_100M_100M_baseline_regular_train_noisy_test \
    CHECKPOINT_FOLDER data/checkpoints/beta_5e-3_100M_100M_baseline_regular_train_noisy_test_eval \
    NUM_PROCESSES 6