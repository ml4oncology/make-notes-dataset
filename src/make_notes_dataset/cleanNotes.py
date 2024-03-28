import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math
from util import extractDateFromNote, extractJobNum

def cleanNotes(dataDir, saveDir):
    """
    Clean processed clinical notes by replacing the date with date in 
    note if available and dropping duplicates according to extracted
    job number and date last updated.

    dataDir: directory path where the merged processed csv file is saved
    saveDir: directory path where the clean merged processed csv file will be saved
    """

    mergedNotes = pd.read_parquet(f'{dataDir}/merged_processed_clinicalNotes.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)

    # extract date from note
    mergedNotes['dateInNote'] = mergedNotes['clinical_notes'].apply( lambda x: extractDateFromNote( x ) )
    mergedNotes['dateInNote'] = pd.to_datetime( mergedNotes['dateInNote'], utc=True, format='mixed', errors='coerce' ) 
    mergedNotes['processed_date'] = mergedNotes['dateInNote'].copy()
    mask_dateOutOfRange = ( mergedNotes['dateInNote'].dt.year < 2004 ) | ( mergedNotes['dateInNote'].dt.year > 2022 )
    mergedNotes.loc[ mask_dateOutOfRange, 'processed_date' ] = mergedNotes.loc[ mask_dateOutOfRange, 'visitDate' ]
    mask_nullDates = mergedNotes['dateInNote'].isnull()
    mergedNotes.loc[ mask_nullDates, 'processed_date' ] = mergedNotes.loc[ mask_nullDates, 'visitDate' ]

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

    print('Number of duplicate records dropped: ', toClean_mergedNotes.shape[0] - filteredRecords.shape[0])

    # filtered notes
    mergedNotesDropDuplicates = pd.concat([mergedNotes.loc[ ~mergedNotes['job_id'].isin(jobIdWDuplicates) ], filteredRecords]).reset_index()

    colsToKeep = ['MRN', 'Observations.ProcName', 'processed_physician_name', 'processed_date', 'clinical_notes', ]
    mergedNotesDropDuplicates[colsToKeep].to_parquet(f'{saveDir}/merged_processed_cleaned_clinicalNotes.parquet.gzip', compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    args = parser.parse_args()

    cleanNotes( args.dataDir, args.saveDir )
