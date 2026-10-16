#!/bin/bash
# Polls SLURM for job statuses and rewrites the run log until all jobs finish.

job_map_file="$1"
run_log_file="$2"
poll_interval="${3:-60}"

if [[ -z "$job_map_file" || -z "$run_log_file" ]]; then
  echo "Usage: $0 <job_map_file> <run_log_file> [poll_interval_seconds]" >&2
  exit 1
fi

terminal_states="COMPLETED|FAILED|CANCELLED|TIMEOUT|NODE_FAIL|OUT_OF_MEMORY"

write_log() {
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  # Query sacct for all job IDs in one call
  local job_ids
  job_ids=$(awk -F'\t' 'NR>1 {print $1}' "$job_map_file" | paste -sd,)

  declare -A status_map exit_map finished_map
  while IFS='|' read -r job_id state exit_code; do
    # sacct can return sub-job lines like 12345678.batch — skip those
    [[ "$job_id" =~ \. ]] && continue
    status_map["$job_id"]="$state"
    exit_map["$job_id"]="$exit_code"
    if [[ "$state" =~ ^($terminal_states)$ ]]; then
      finished_map["$job_id"]=$(date '+%Y-%m-%d %H:%M:%S')
    fi
  done < <(sacct -j "$job_ids" --format=JobID,State,ExitCode --noheader --parsable2 2>/dev/null)

  {
    echo "=== Deid run: $(basename "$job_map_file" .tsv) ==="
    echo "Job map:     $job_map_file"
    echo "Last update: $timestamp"
    echo ""
    printf "%-12s  %-40s  %7s  %12s  %-16s  %9s  %s\n" \
      "job_id" "part_file" "n_rows" "total_chars" "status" "exit_code" "finished_at"
    printf "%-12s  %-40s  %7s  %12s  %-16s  %9s  %s\n" \
      "------------" "----------------------------------------" "-------" "------------" "----------------" "---------" "-------------------"

    local total=0 done_count=0
    while IFS=$'\t' read -r job_id part_file n_rows total_chars; do
      [[ "$job_id" == "job_id" ]] && continue  # skip header
      (( total++ )) || true
      local state="${status_map[$job_id]:-PENDING}"
      local exit_code="${exit_map[$job_id]:--}"
      local finished="${finished_map[$job_id]:--}"
      [[ "$state" =~ ^($terminal_states)$ ]] && (( done_count++ )) || true
      printf "%-12s  %-40s  %7s  %12s  %-16s  %9s  %s\n" \
        "$job_id" "$part_file" "$n_rows" "$total_chars" "$state" "$exit_code" "$finished"
    done < "$job_map_file"

    echo ""
    echo "Progress: ${done_count}/${total} jobs finished"
  } > "$run_log_file"

  echo "$done_count $total"
}

echo "Watching $(awk -F'\t' 'NR>1' "$job_map_file" | wc -l | tr -d ' ') jobs. Log: $run_log_file"

while true; do
  read -r done_count total <<< "$(write_log)"
  if [[ "$done_count" -eq "$total" && "$total" -gt 0 ]]; then
    echo "All $total jobs finished. Final log: $run_log_file"
    exit 0
  fi
  sleep "$poll_interval"
done

