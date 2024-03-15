#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/2Blast_part4_statuses_dates_zips/processed/PatientList"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/2Blast_part4_statuses_dates_zips/processed/PatientList"

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/mergePatientListJSON.py $dataDir $saveDir 0 598" 