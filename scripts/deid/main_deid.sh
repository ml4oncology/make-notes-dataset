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

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <data_pull_date>"
    exit 1
fi

data_pull_date="$1"

if [[ $data_pull_date == "2024-06-04" ]]; then
  # old pull
  df_name=merged_processed_cleaned_clinical_notes_medonc_only.parquet.gzip

elif [[ $data_pull_date == "2025-01-08" ]]; then
  # new pull
  df_name=merged_processed_cleaned_clinical_notes_medonc_only_epic_records_only.parquet.gzip

else
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi

data_dir="${PROCESSED_DATA_BASE}/data_pull_${data_pull_date}"

chunk_size=500

# Step 1: Split the dataframe
echo "Splitting dataframe..."
split_files=$(python3 ../../src/extract/split_dataframe.py "$data_dir" "$df_name" "$chunk_size")

# Step 2: Create output directories
mkdir -p logs

# Step 3: Submit jobs
echo "Submitting jobs..."
for f in $split_files; do
  df_name=$(basename "$f")
  sbatch job_template_deid.sh "$data_dir/splits" "$df_name"
done

echo "All jobs submitted."
