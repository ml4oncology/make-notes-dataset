#!/bin/bash
#export PATH="$HOME"
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

save_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
mrn_file="/cluster/home/t127556uhn/misc/mrn_map_2Blast_part4.csv"

data_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_parquet_gzip_notes_p1"
json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_json_p1"
missing_notes=0
file_part_num=0
pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/process_notes.py $data_dir $json_dir $save_dir $mrn_file $missing_notes $file_part_num"

data_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_parquet_gzip_notes_p2"
json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_json_p2"
missing_notes=1
file_part_num=0
pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/process_notes.py $data_dir $json_dir $save_dir $mrn_file $missing_notes $file_part_num"