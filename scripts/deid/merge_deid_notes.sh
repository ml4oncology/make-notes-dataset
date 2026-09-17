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

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "Usage: $0 <data_pull_date> <df_name> [<data_label>]"
    exit 1
fi

data_pull_date="$1"
df_name="$2"
data_label="$3"

userName="$CLUSTER_USERNAME"
memory=16
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-04:00:00"
partition="all"

deid_dir="${PROCESSED_DATA_BASE}/data_pull_${data_pull_date}${data_label:+_${data_label}}/splits"

../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/deid/merge_deid_dataframes.py $deid_dir $df_name"