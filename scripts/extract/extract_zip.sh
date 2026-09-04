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

userName="$CLUSTER_USERNAME"
memory=16
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-03:00:00"
partition="all"

# Determine data directory based on pull date
data_pull_date="$1"

data_dir="${RAW_DATA_BASE}/data_pull_${data_pull_date}"
if [[ $data_pull_date != "2024-06-04" && $data_pull_date != "2025-01-08" ]]; then
    echo "Invalid data_pull_date: $data_pull_date. Use '2024-06-04' or '2025-01-08'"
    exit 1
fi

# --------------------------------------------------
# Extract observation JSON zipped files
# --------------------------------------------------
zip_dir=${data_dir}/observation_json_zip
output_dir=${data_dir}/observation_json
../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/extract/extract_zip.py $zip_dir $output_dir"

# --------------------------------------------------
# Extract clinic notes JSON zipped files
# --------------------------------------------------
zip_dir=${data_dir}/clinic_notes_json_zip
output_dir=${data_dir}/clinic_notes_json
../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/extract/extract_zip.py $zip_dir $output_dir"

# --------------------------------------------------
# Extract observation CSV zipped files (batched)
# --------------------------------------------------
zip_dir=${data_dir}/observation_csv_zip
output_dir=${data_dir}/observation_parquet
total_batches=100
for ((i=0; i<total_batches; i++)); do
    ../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/extract/extract_zip.py $zip_dir $output_dir --batch_index $i --total_batches $total_batches" 
done

# --------------------------------------------------
# Extract clinic notes CSV zipped files
# --------------------------------------------------
zip_dir=${data_dir}/clinic_notes_csv_zip
output_dir=${data_dir}/clinic_notes_parquet
../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/extract/extract_zip.py $zip_dir $output_dir"
