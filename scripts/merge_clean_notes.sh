#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-02:00:00"
partition="all"

parquet_gzip_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
file_part_max_obs=598
file_part_max_clin=598

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/merge_clean_notes.py $parquet_gzip_dir $file_part_max_obs $file_part_max_clin"
