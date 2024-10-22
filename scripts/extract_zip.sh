#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0
run_time="0-01:00:00"
partition="all"

data_dir=/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04

zip_dir=${data_dir}/zip_json_p1
output_dir=${data_dir}/raw_json_p1

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_json_p2
output_dir=${data_dir}/raw_json_p2

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_notes_p1
output_dir=${data_dir}/raw_parquet_gzip_notes_p1

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 

zip_dir=${data_dir}/zip_notes_p2
output_dir=${data_dir}/raw_parquet_gzip_notes_p2

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/extract_zip.py $zip_dir $output_dir" 