#!/bin/bash
#export PATH="$HOME"
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/missing_notes_csv/raw"
jsonDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/notes_zips"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/missing_notes_csv/processed/dataframes"
MRNfile="/cluster/home/t127556uhn/misc/mrn_map_2Blast_part4.csv"

for id in {0..598}
do

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/processMissingNotes.py $dataDir $jsonDir $saveDir $MRNfile $id" 

done
