#!/bin/bash

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/OncoTRAIL/bin/python"
nGPU=0
run_time="0-04:00:00"
partition="all"
nCPU=4

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

save_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_${data_pull_date}"

case "$dir_type" in
    observation)
        json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_${data_pull_date}/observation_json"
        clinic_notes=0
        ;;
    clinic)
        json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_${data_pull_date}/clinic_notes_json"
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
        upper_limit=1775
        case "$dir_type" in
            observation) 
                file_name="2Blast_part5_file-part-num_observations.parquet.gzip"
                ;;
            clinic)      
                file_name="2Blast_part5_file-part-num_clinic_notes.parquet.gzip"  
                ;;
        esac
        ;;
    "2024-06-04")
        upper_limit=598
        case "$dir_type" in
            observation) 
                file_name="2Blast_part4_file-part-num_results_with_status_dates.parquet.gzip" 
                ;;
            clinic)      
                file_name="2Blast_part4_file-part-num_clinic_notes.parquet.gzip"             
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
        "../../src/extract/build_last_updated.py ${json_dir} ${save_dir} ${clinic_notes} ${file_name} ${upper_limit} ${nCPU}"
