#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataPath="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes/merged_processed_cleaned_clinicalNotes_2008-01-01_2017-12-31.parquet.gzip"
treatmentDataPath="/cluster/home/t127556uhn/gitrepo/2024/make-clinical-dataset/data/processed/treatment_centered_clinical_dataset.parquet.gzip"
targetDataPath="/cluster/home/t127556uhn/gitrepo/2024/make-clinical-dataset/data/interim/emergency_room_visit.parquet.gzip"
saveDir="/cluster/home/t127556uhn/gitrepo/2024/make-notes-dataset/data"
configName="mostRecentVisit_medOnc_ConsultLetterClinic"
testStartDate="2015-01-01"
testEndDate="2017-12-31"
eventName="ED_visit"
lookbackWindow=30

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/anchorNoteTreatmentDate.py $dataPath $treatmentDataPath $targetDataPath $saveDir $configName $testStartDate $testEndDate $eventName $lookbackWindow" 