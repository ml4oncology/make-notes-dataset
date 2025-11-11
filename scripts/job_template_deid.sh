#!/bin/bash
#SBATCH -p gpu
#SBATCH --gres=gpu:1
#SBATCH --mem 8GB
#SBATCH -t 0-08:00:00
#SBATCH -A grantgroup_gpu
#SBATCH -J deid_part
#SBATCH -o logs/%x_%j.out
#SBATCH -e logs/%x_%j.err

# Load apptainer and environment
module load apptainer

# Arguments
data_dir=$1
df_name=$2

# Call your existing docker script
./helper_deid.sh "$data_dir" "$df_name"
