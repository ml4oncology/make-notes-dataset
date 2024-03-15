#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/2Blast_part4_statuses_dates_zips/raw"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/2Blast_part4_statuses_dates_zips/processed/PatientList"

for id in {0..598}
do

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/extractPatientIDJSON.py $dataDir $saveDir $id" 

done