#!/bin/bash
export PATH=$PATH:$(pwd)

userName="t127556uhn"
memory=16
condaEnv="~/miniforge3/envs/basic/bin/python"
nGPU=0

# dataPath="/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes/merged_processed_cleaned_clinicalNotes_2008-01-01_2017-12-31.parquet.gzip"
# #treatmentDataPath="/cluster/home/t127556uhn/gitrepo/2024/make-clinical-dataset/data/processed/treatment_centered_clinical_dataset.parquet.gzip"
# treatmentDataPath="/cluster/projects/gliugroup/2BLAST/final_dataset/treatment_centered_clinical_dataset.parquet.gzip"
# EDVisitDataDir="/cluster/projects/gliugroup/2BLAST/final_dataset/data/interim"
# symptomDataDir="/cluster/projects/gliugroup/2BLAST/final_dataset/data/interim" 
# lastSeenDataDir="/cluster/projects/gliugroup/2BLAST/final_dataset/data/processed"
# saveDir="/cluster/home/t127556uhn/gitrepo/2024/make-notes-dataset/data"
# testEndDate="2017-12-31"
# lookbackWindow=30

# configName="mostRecentVisit-medOnc-ConsultLetterClinic"
# pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/anchorNoteTreatmentDate.py $dataPath $treatmentDataPath $EDVisitDataDir $symptomDataDir $lastSeenDataDir $saveDir $configName $testEndDate $lookbackWindow" 

# configName="mostRecentVisit-appendFirst-medOnc-ConsultLetterClinic"
# pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/anchorNoteTreatmentDate.py $dataPath $treatmentDataPath $EDVisitDataDir $symptomDataDir $lastSeenDataDir $saveDir $configName $testEndDate $lookbackWindow" 

# configName="firstVisitOnly-medOnc-ConsultLetterClinic"
# pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/anchorNoteTreatmentDate.py $dataPath $treatmentDataPath $EDVisitDataDir $symptomDataDir $lastSeenDataDir $saveDir $configName $testEndDate $lookbackWindow" 

dataPath="/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/HealthReportRecords/results_status_dates/processed/dataframes/merged_processed_cleaned_clinicalNotes_2008-01-01_2017-12-31.parquet.gzip"
treatmentDataPath="/cluster/projects/gliugroup/2BLAST/data/final/treatment_centered_clinical_dataset.parquet.gzip"
EDVisitDataDir="/cluster/projects/gliugroup/2BLAST/data/final/data/interim"
symptomDataDir="/cluster/projects/gliugroup/2BLAST/data/final/data/interim" 
lastSeenDataDir="/cluster/projects/gliugroup/2BLAST/data/final/data/processed"
saveDir="/cluster/home/t127556uhn/gitrepo/2024/make-notes-dataset/debug_data"
testEndDate="2017-12-31"
lookbackWindow=30

configName="firstVisitOnly-medOnc-ConsultLetterClinic"
pySLURMargs.py $userName $memory $condaEnv $nGPU "../src/make_notes_dataset/anchorNoteTreatmentDate.py $dataPath $treatmentDataPath $EDVisitDataDir $symptomDataDir $lastSeenDataDir $saveDir $configName $testEndDate $lookbackWindow" 
