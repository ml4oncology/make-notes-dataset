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

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 <data_pull_date> [<data_label>]"
    exit 1
fi

data_pull_date="$1"
data_label="$2"

userName="$CLUSTER_USERNAME"
memory=16
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-04:00:00"
partition="all"

if [[ $data_pull_date == "2024-06-04" || $data_pull_date == "2025-01-08" ]]; then
    parquet_gzip_dir="${PROCESSED_DATA_BASE}/data_pull_${data_pull_date}${data_label:+_${data_label}}"
else
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi
obs_notes_dir="${parquet_gzip_dir}/obs_notes_parts"
clinic_notes_dir="${parquet_gzip_dir}/clinic_notes_parts"
../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/notes_pipeline/merge_clean_notes.py $parquet_gzip_dir $obs_notes_dir $clinic_notes_dir"
