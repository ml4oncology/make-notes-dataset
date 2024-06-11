#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

dataDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/missing_notes_csv/processed/dataframes"
saveDir="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/missing_notes_csv/processed/dataframes"

pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/mergeMissingNotes.py $dataDir $saveDir 0 598" 