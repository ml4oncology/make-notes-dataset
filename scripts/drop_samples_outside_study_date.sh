#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0
run_time="0-01:00:00"
partition="all"

data_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
save_dir="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04"
start_date="2008-01-01"
end_date="2017-12-31"

pySLURMargs.py $userName $memory $condaEnv $nGPU $run_time $partition "../src/drop_samples_outside_study_date.py $data_dir $save_dir $start_date $end_date"
