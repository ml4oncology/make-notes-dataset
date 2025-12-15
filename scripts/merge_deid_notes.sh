#!/bin/bash
export PATH=$PATH:$(pwd)

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <data_pull_date>"
    exit 1
fi

data_pull_date="$1"

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-04:00:00"
partition="all"

if [[ $data_pull_date == "2024-06-04" ]]; then
    # old pull
    deid_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04/splits"
elif [[ $data_pull_date == "2025-01-08" ]]; then
    # new pull
    deid_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2025-01-08/splits"
else
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/merge_deid_dataframes.py $deid_dir"