#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-03:00:00"
partition="all"

data_dir=/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2025-01-08
# data_dir=/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04

# zip_dir=${data_dir}/observation_json_zip
# output_dir=${data_dir}/observation_json

# pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

# zip_dir=${data_dir}/clinic_notes_json_zip
# output_dir=${data_dir}/clinic_notes_json

# pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/observation_csv_zip
output_dir=${data_dir}/observation_parquet

total_batches=100
for ((i=0; i<total_batches; i++)); do
    pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir --batch_index $i --total_batches $total_batches" 
done

# zip_dir=${data_dir}/clinic_notes_csv_zip
# output_dir=${data_dir}/clinic_notes_parquet

# pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 