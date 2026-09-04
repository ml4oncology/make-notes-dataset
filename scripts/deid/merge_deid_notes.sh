#!/bin/bash
# Load paths from .env (gitignored; see .env.example)
_env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.env"
if [[ ! -f "$_env_file" ]]; then
    echo "Error: $_env_file not found. Copy .env.example to .env." >&2
    exit 1
fi
set -a
source "$_env_file"
set +a

export PATH=$PATH:$(pwd)

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <data_pull_date>"
    exit 1
fi

data_pull_date="$1"

userName="$CLUSTER_USERNAME"
memory=16
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-04:00:00"
partition="all"

if [[ $data_pull_date != "2024-06-04" && $data_pull_date != "2025-01-08" ]]; then
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi

deid_dir="${PROCESSED_DATA_BASE}/data_pull_${data_pull_date}/splits"

../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/deid/merge_deid_dataframes.py $deid_dir"