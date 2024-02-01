#!/bin/bash
#export PATH="$HOME"
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/anaconda3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/raw"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes"
MRNfile="/cluster/home/t127556uhn/misc/mrn_map_2Blast_part4.csv"

for id in {0..598}
do

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/processClinicalNotes.py $dataDir $saveDir $MRNfile $id" 

done
