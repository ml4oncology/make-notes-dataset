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

set -e

# Input variables
# Usage: main_deid.sh <data_pull_date> <df_name> [<data_label>] [<chunk_size>] [<run_time_hours>]

if [[ $# -lt 2 || $# -gt 5 ]]; then
    echo "Usage: $0 <data_pull_date> <df_name> [<data_label>] [<chunk_size>] [<run_time_hours>]"
    exit 1
fi

data_pull_date="$1"
df_name="$2"
data_label="$3"
chunk_size="${4:-500}"
run_time_hours="${5:-8}"

data_dir="${PROCESSED_DATA_BASE}/data_pull_${data_pull_date}${data_label:+_${data_label}}"

# Step 1: Split the dataframe
echo "Splitting dataframe..."
split_files=$(python3 ../../src/extract/split_dataframe.py "$data_dir" "$df_name" "$chunk_size")

# Step 2: Create output directories
mkdir -p logs

# Step 3: Submit jobs
echo "Submitting jobs..."
for f in $split_files; do
  df_name=$(basename "$f")
  sbatch --time "0-${run_time_hours}:00:00" job_template_deid.sh "$data_dir/splits" "$df_name"
done

echo "All jobs submitted."
