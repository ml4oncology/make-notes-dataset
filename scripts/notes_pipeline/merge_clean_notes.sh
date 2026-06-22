#!/bin/bash
export PATH=$PATH:$(pwd)

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <data_pull_date>"
    exit 1
fi

data_pull_date="$1"

userName="t127556uhn"
memory=64
condaEnv="~/miniforge3/envs/OncoTRAIL/bin/python"
nGPU=0
run_time="0-04:00:00"
partition="superhimem"

if [[ $data_pull_date == "2024-06-04" ]]; then
    parquet_gzip_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
    file_part_max_obs=598
    file_part_max_clin=598

elif [[ $data_pull_date == "2025-01-08" ]]; then
    parquet_gzip_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2025-01-08"
    file_part_max_obs=1775
    file_part_max_clin=1775

else
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi

../pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../../src/notes_pipeline/merge_clean_notes.py $parquet_gzip_dir $file_part_max_obs $file_part_max_clin"
