import numpy as np
import pandas as pd
import argparse
from pathlib import Path
from util import extractDateFromNote, extractJobNum

def merge_clean_notes(dataDir, saveDir, filePartMin, filePartMax):
    """
    Merge processed clinical notes csv into a parquet file for compression.

    dataDir: directory path where the processed csv files are saved
    saveDir: directory path where merged parquet file will be saved
    filePartMin: minimum file part number of files to be merged
    filePartMax: maximum file part number of files to be merged

    Clean processed clinical notes by replacing the date with date in 
    note if available and dropping duplicates according to extracted
    job number and date last updated.

    dataDir: directory path where the merged processed csv file is saved
    saveDir: directory path where the clean merged processed csv file will be saved
    """

    mergedNotesList = []
    for ctr in range(filePartMin, filePartMax + 1):
        # load dataframe
        dfTemp = pd.read_csv( f"{dataDir}/processedClinicalNotes_{ctr}.csv", index_col = 0 )
        mergedNotesList.append( dfTemp )

    mergedNotes = pd.concat( mergedNotesList )
    # mergedNotes['e_mail_address'] = mergedNotes['e_mail_address'].astype(str)

    mergedNotes['visitDate'] = pd.to_datetime( mergedNotes['visitDate'], utc=True )
    mergedNotes['lastUpdated'] = pd.to_datetime( mergedNotes['lastUpdated'].apply( lambda x: x.replace('T', ' ').replace('Z','')[:19] ),\
                                                 utc=True, format='%Y-%m-%d %H:%M:%S' )

    mergedNotes.to_parquet(f'{saveDir}/merged_processed_clinicalNotes.parquet.gzip', compression='gzip', index=False)

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

    colsToKeep = ['MRN', 'Observations.ProcName', 'processed_physician_name', 'processed_date', 'clinical_notes', 'EPRDate']
    mergedNotesDropDuplicates[colsToKeep].to_parquet(f'{saveDir}/merged_processed_cleaned_clinicalNotes.parquet.gzip', compression='gzip', index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartMin", help = "file part number minimum", type = int) # minimum file part number
    parser.add_argument("filePartMax", help = "file part number maximum", type = int) # maximum file part number
    args = parser.parse_args()

    merge_clean_notes( args.dataDir, args.saveDir, args.filePartMin, args.filePartMax )
