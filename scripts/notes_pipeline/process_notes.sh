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

userName="$CLUSTER_USERNAME"
memory=64
condaEnv="$CONDA_PYTHON"
nGPU=0
run_time="0-04:00:00"
partition="veryhimem"
nCPU=1

# ---------------------------------------------------------------------------
# Usage: process_notes.sh <data_pull_date> <dir_type>
#   dir_type  -- "observation" or "clinic"
# ---------------------------------------------------------------------------
if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <data_pull_date> <dir_type>"
    echo "  dir_type: observation | clinic"
    exit 1
fi

data_pull_date="$1"
dir_type="$2"

case "$dir_type" in
    observation)
        data_dir="${RAW_DATA_BASE}/data_pull_${data_pull_date}/observation_parquet"
        save_dir="${PROCESSED_DATA_BASE}/${data_pull_date}/obs_notes_parts"
        last_updated_csv_path="${RAW_DATA_BASE}/data_pull_${data_pull_date}/last_updated_observation.csv"
        clinic_notes=0
        ;;
    clinic)
        data_dir="${RAW_DATA_BASE}/data_pull_${data_pull_date}/clinic_notes_parquet"
        save_dir="${PROCESSED_DATA_BASE}/${data_pull_date}/clinic_notes_parts"
        last_updated_csv_path="${RAW_DATA_BASE}/data_pull_${data_pull_date}/last_updated_clinic.csv"
        clinic_notes=1
        ;;
    *)
        echo "Error: dir_type must be 'observation' or 'clinic', got '${dir_type}'"
        exit 1
        ;;
esac

# Determine upper_limit and file_name from data_pull_date.
case "$data_pull_date" in
    "2025-01-08")
        mrn_file="${MRN_MAP_DIR}/mrn_map_2Blast_part5.csv"
        case "$dir_type" in
            observation) 
                file_glob="2Blast_part5_*_observations.parquet.gzip" 
                ;;
            clinic)       
                file_glob="2Blast_part5_*_clinic_notes.parquet.gzip"
                ;;
        esac
        ;;
    "2024-06-04")
        mrn_file="${MRN_MAP_DIR}/mrn_map_2Blast_part4.csv"
        case "$dir_type" in
            observation)  
                file_glob="2Blast_part4_*_num_results_with_status_dates.parquet.gzip"
                ;;
            clinic)      
                file_glob="2Blast_part4_*_clinic_notes.parquet.gzip"                
                ;;
        esac
        ;;
    *)
        echo "Error: unsupported data_pull_date '${data_pull_date}'" >&2
        exit 1
        ;;
esac

../pySLURMargs.py "$userName" "$memory" "$condaEnv" "$nGPU" \
        "$run_time" "$partition" "$nCPU" \
        "../../src/notes_pipeline/process_notes.py ${data_dir} ${save_dir} ${mrn_file} ${clinic_notes} ${file_glob} ${last_updated_csv_path}"
