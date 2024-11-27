#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-01:00:00"
partition="all"

data_dir=/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04

zip_dir=${data_dir}/zip_json_observations
output_dir=${data_dir}/raw_json_observations

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_json_clinic
output_dir=${data_dir}/raw_json_clinic

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_notes_observations
output_dir=${data_dir}/raw_parquet_gzip_notes_observations

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_notes_clinic
output_dir=${data_dir}/raw_parquet_gzip_notes_clinic

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 