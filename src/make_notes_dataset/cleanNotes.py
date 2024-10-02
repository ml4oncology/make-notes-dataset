import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math
from util import extractDateFromNote, extractJobNum, stripTitle

def cleanNotes(dataDir, saveDir, includeMissing=0, missingNotesDir=None):
    """
    Clean processed clinical notes by replacing the date with date in 
    note if available and dropping duplicates according to extracted
    job number and date last updated.

    dataDir: directory path where the merged processed csv file is saved
    saveDir: directory path where the clean merged processed csv file will be saved
    """

    print(includeMissing)
    
    mergedNotes = pd.read_parquet(f'{dataDir}/merged_processed_clinicalNotes.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)
    colsToKeep = ['MRN', 'Observations.ProcName', 'clinical_notes', 'visitDate', 'processed_physician_name', 'lastUpdated', 'dictated_by']
    mergedNotes = mergedNotes[colsToKeep].copy()

    if includeMissing == 1:
        # load file
        missingNotes = pd.read_parquet(f'{missingNotesDir}/merged_processed_missingClinicalNotes.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)
        colsToKeep = ['MRN', 'ClinicNotes.ClinicNote.code.text', 'clinical_notes', 'visitDate', 'processed_physician_name', 'lastUpdated', 'dictated_by']
        missingNotes = missingNotes[colsToKeep].copy()
        missingNotes.rename(columns={"ClinicNotes.ClinicNote.code.text":"Observations.ProcName"}, inplace=True)
        mergedNotes = pd.concat([mergedNotes, missingNotes], ignore_index=True)

    # add physician name
    maskNotNull = mergedNotes['dictated_by'].notnull()
    mergedNotes.loc[maskNotNull, 'dictated_by'] = mergedNotes.loc[maskNotNull, 'dictated_by'].apply(lambda x: stripTitle(x))

    # extract date from note
    mergedNotes['dateInNote'] = mergedNotes['clinical_notes'].apply( lambda x: extractDateFromNote( x ) )
    mergedNotes['dateInNote'] = pd.to_datetime( mergedNotes['dateInNote'], utc=True, format='mixed', errors='coerce' ) 
    mergedNotes['processed_date'] = mergedNotes['dateInNote'].copy()
    mask_dateOutOfRange = ( mergedNotes['dateInNote'].dt.year < 2004 ) | ( mergedNotes['dateInNote'].dt.year > 2022 )
    mergedNotes.loc[ mask_dateOutOfRange, 'processed_date' ] = mergedNotes.loc[ mask_dateOutOfRange, 'visitDate' ]
    mask_nullDates = mergedNotes['dateInNote'].isnull()
    mergedNotes.loc[ mask_nullDates, 'processed_date' ] = mergedNotes.loc[ mask_nullDates, 'visitDate' ]
    mergedNotes.rename(columns={"visitDate": "EPRDate"}, inplace=True)

    # check that there is no-nan entry in the processed date
    assert sum( mergedNotes['processed_date'].isnull() ) == 0 , "There is a nan date in the processed dates."

    # delete duplicates
    mergedNotes['job_id'] = mergedNotes['clinical_notes'].apply( lambda x: extractJobNum(x) )
    # find notes with duplicity more than 1
    dfWithJobID = mergedNotes.loc[ mergedNotes['job_id'].notnull() ].copy()
    dfJobIDCount = dfWithJobID.groupby(['job_id']).size().reset_index( name='job_id_count' )
    jobIdWDuplicates = list( dfJobIDCount.loc[ dfJobIDCount['job_id_count'] > 1 ]['job_id'].unique() )
    
    toClean_mergedNotes = mergedNotes.loc[ mergedNotes['job_id'].isin(jobIdWDuplicates) ].copy()
    toClean_mergedNotes.sort_values(by='lastUpdated', ascending=False, inplace=True)
    # group by MRN, procedure name, and job id
    filteredRecords = toClean_mergedNotes.groupby(['MRN', 'Observations.ProcName', 'job_id']).first().reset_index()

    # check that for the same job id and procedure name, there are no duplicates anymore
    dfWithJobID = filteredRecords.loc[ filteredRecords['job_id'].notnull() ].copy()
    dfJobIDCount = dfWithJobID.groupby(['MRN', 'Observations.ProcName', 'job_id']).size().reset_index( name='job_id_count' )
    assert dfJobIDCount['job_id_count'].max() == 1, "There is a duplicate record with the same procedure name."
    
    print('Number of duplicate records dropped: ', toClean_mergedNotes.shape[0] - filteredRecords.shape[0])

    # filtered notes
    mergedNotesDropDuplicates = pd.concat([mergedNotes.loc[ ~mergedNotes['job_id'].isin(jobIdWDuplicates) ], filteredRecords]).reset_index()

    colsToKeep = ['MRN', 'Observations.ProcName', 'processed_physician_name', 'processed_date', 'clinical_notes', 'EPRDate', 'dictated_by']
    if includeMissing == 0:
        fileName = 'merged_processed_cleaned_clinicalNotes'
    else:
        fileName = 'merged_processed_cleaned_clinicalNotes_addedMissing'
    mergedNotesDropDuplicates[colsToKeep].to_parquet(f'{saveDir}/{fileName}.parquet.gzip', compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("--includeMissing", help = "include missing notes and merge", type = int) # include missing notes
    parser.add_argument("--missingDataDir", help = "directory of missing data", type = str) # directory of missing data
    args = parser.parse_args()

    cleanNotes( args.dataDir, args.saveDir, args.includeMissing, args.missingDataDir )
