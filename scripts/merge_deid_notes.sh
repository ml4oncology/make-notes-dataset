#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-04:00:00"
partition="all"

# deid_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04/splits"
deid_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2025-01-08/splits"

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/merge_deid_dataframes.py $deid_dir"
