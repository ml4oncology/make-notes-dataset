#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0
run_time="1-00:00:00"
partition="himem"

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes"

data_dir_obs="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_parquet_gzip_notes_p1"
data_dir_clin="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_parquet_gzip_notes_p2"
json_dir_obs="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_json_p1"
json_dir_clin="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/raw_json_p2"
mrn_file="/cluster/home/t127556uhn/misc/mrn_map_2Blast_part4.csv"
save_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
file_part_max_obs=598
file_part_max_clin=598

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/merge_clean_notes.py $data_dir_obs $data_dir_clin $json_dir_obs $json_dir_clin $mrn_file $save_dir $file_part_max_obs $file_part_max_clin"