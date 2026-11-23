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

# Step 1: Create output directories and split the dataframe
run_ts=$(date +%Y%m%d_%H%M%S)
log_dir="logs/${run_ts}"
mkdir -p logs "$log_dir"
split_sizes_file="${log_dir}/split_sizes.tsv"

echo "Splitting dataframe..."
split_files=$("$CONDA_PYTHON" ../../src/extract/split_dataframe.py "$data_dir" "$df_name" "$chunk_size")

echo -e "part_file\tn_rows\ttotal_chars" > "$split_sizes_file"
while IFS=$'\t' read -r f n_rows total_chars; do
  echo -e "$(basename "$f")\t${n_rows}\t${total_chars}" >> "$split_sizes_file"
done <<< "$split_files"
echo "Split sizes written to $split_sizes_file"

# Step 3: Submit jobs
echo "Submitting jobs..."
job_map_file="${log_dir}/job_id_map.tsv"
run_log_file="${log_dir}/run_log.txt"
echo -e "job_id\tpart_file\tn_rows\ttotal_chars" > "$job_map_file"
while IFS=$'\t' read -r f n_rows total_chars; do
  df_name=$(basename "$f")
  job_output=$(sbatch --time "0-${run_time_hours}:00:00" \
    --output "logs/%x_%j.out" --error "logs/%x_%j.err" \
    job_template_deid.sh "$data_dir/splits" "$df_name")
  echo "$job_output"
  job_id=$(echo "$job_output" | awk '{print $NF}')
  echo -e "${job_id}\t${df_name}\t${n_rows}\t${total_chars}" >> "$job_map_file"
done <<< "$split_files"

echo "All jobs submitted. Job ID map written to $job_map_file"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Step 4: Submit a finalizer job that writes the final run log after all jobs finish
abs_job_map_file="$(cd "$(dirname "$job_map_file")" && pwd)/$(basename "$job_map_file")"
abs_run_log_file="$(cd "$(dirname "$run_log_file")" && pwd)/$(basename "$run_log_file")"
abs_log_dir="$(cd "$log_dir" && pwd)"
dep_ids=$(awk -F'\t' 'NR>1 && $1 ~ /^[0-9]+$/ {print $1}' "$job_map_file" | paste -sd:)
if [[ -n "$dep_ids" ]]; then
  finalizer_output=$(sbatch --job-name=deid_finalize --dependency="afterany:${dep_ids}" \
    --time=00:10:00 --mem=1G --cpus-per-task=1 \
    --output "${abs_log_dir}/finalize_%j.out" --error "${abs_log_dir}/finalize_%j.err" \
    --wrap "sleep 30; bash '$script_dir/watch_deid_run.sh' '$abs_job_map_file' '$abs_run_log_file' --once")
  echo "$finalizer_output"
  echo "Finalizer job will write the final run log after all jobs end."
else
  echo "Warning: no valid job IDs found; skipping finalizer job." >&2
fi

# Step 5: Launch background watcher for live progress updates
nohup bash "$script_dir/watch_deid_run.sh" "$job_map_file" "$run_log_file" \
  > "${log_dir}/watcher.log" 2>&1 &
echo "Run log: $run_log_file (watcher PID: $!)"
