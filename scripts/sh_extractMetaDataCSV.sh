#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=4
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/raw"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/EDA"

for id in {0..598}
do

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/extractMetaDataCSV.py $dataDir $saveDir $id" 

done