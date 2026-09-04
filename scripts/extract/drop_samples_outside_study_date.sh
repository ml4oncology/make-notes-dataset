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
memory=4
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-01:00:00"
partition="all"

if [[ $data_pull_date == "2024-06-04" ]]; then
    data_dir="${PROCESSED_DATA_BASE}/data_pull_2024-06-04"
    save_dir="${PROCESSED_DATA_BASE}/data_pull_2024-06-04"
    notes_file="merged_processed_cleaned_clinical_notes.parquet.gzip"
    start_date="2008-01-01"
    end_date="2017-12-31"
else
    echo "Error: data_pull_date '${data_pull_date}' not implemented yet." >&2
    exit 1
fi

../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/extract/drop_samples_outside_study_date.py $data_dir $save_dir $notes_file $start_date $end_date"
