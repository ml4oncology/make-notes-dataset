#!/bin/bash
#export PATH="$HOME"
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/LLMfinetune/bin/python"
nGPU=0
run_time="0-01:00:00"
partition="all"

save_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
mrn_file="/cluster/home/t127556uhn/misc/mrn_map_2Blast_part4.csv"

data_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/observation_parquet"
json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/observation_json"
clinic_notes=0
upper_limit=598
for ((i=0; i<=upper_limit; i++))
do
    pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/process_notes.py $data_dir $json_dir $save_dir $mrn_file $clinic_notes $i"
done

data_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/clinic_notes_parquet"
json_dir="/cluster/projects/gliugroup/2BLAST/data/raw/data_pull_2024-06-04/clinic_notes_json"
clinic_notes=1
upper_limit=598
for ((i=0; i<=upper_limit; i++))
do
    pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/process_notes.py $data_dir $json_dir $save_dir $mrn_file $clinic_notes $i"
done
