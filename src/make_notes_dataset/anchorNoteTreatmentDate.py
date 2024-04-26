import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math
import re
import sys
from make_clinical_dataset import combine_feat_to_main_data
from preduce import get_change_since_prev_session, get_event_labels, create_train_val_test_splits, exclude_immediate_events

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/constants")
# load constants from file
from constants import aliasDictionary

def anchorNoteTreatmentDate(dataPath, treatmentDataPath, targetDataPath, saveDir, configName,\
                            testEndDate, eventName, lookbackWin):
    """
        Anchor the note to treatment date depending on specified configuration.
        Generate train, validation, test split.

        dataPath: file path of the notes data
        treatmentDataPath: file path of the treatment data frame
        targetDataPath: file path of the target data frame
        saveDir: directory path where processed data frame will be saved
        configName: configuration name for how to anchor note to treatment date
        testEndDate: ending date for the test time period (and end date of the study period)
        eventName: name of event
        lookbackWin: lookback window for the notes to be anchored to treatment date
    """

    # load notes file
    mergedNotes = pd.read_parquet(f'{dataPath}', engine='pyarrow', use_nullable_dtypes = True)

    # load treatment-centered data frame
    df_treat = pd.read_parquet(f'{treatmentDataPath}', engine='pyarrow', use_nullable_dtypes = True)

    # load target data frame
    df_target = pd.read_parquet(f'{targetDataPath}', engine='pyarrow', use_nullable_dtypes = True)

    if configName == 'mostRecentVisit_medOnc_ConsultLetterClinic':
        # only consider notes written by a medical oncologist 
        # only consider consultation, letter, clinic notes
        medOncs = list(set(aliasDictionary.values()))
        procName = ['Clinic Note', 'Letter', 'History & Physical Note', 'Consultation Note']
        mergedNotes = mergedNotes.loc[ (mergedNotes['processed_physician_name'].isin( medOncs )) &\
                                       (mergedNotes['Observations.ProcName'].isin( procName )) ].copy()
    else:
        raise Exception("Not implemented yet.")
    
    # merge records of patient on the same day
    # take the maximum of the EPR dates

    mergedNotes['note'] = mergedNotes['Observations.ProcName'] + ':\n' + mergedNotes['clinical_notes']
    mergedNotes = mergedNotes.groupby(['MRN','processed_date']).agg(
                    processed_note=('note', lambda x: '\n'.join(x)),
                    maxEPRdate=('EPRDate', 'max')).reset_index()
    mergedNotes.rename(columns={"MRN": "mrn", "processed_note": "note"}, inplace=True)
    mergedNotes['processed_date'] = mergedNotes['processed_date'].dt.date
    mergedNotes['processed_date'] = mergedNotes['processed_date'].astype('<M8[ns]')

    # filter the treatment-centered data frame
    df_treat = df_treat.loc[ df_treat['mrn'].isin( mergedNotes['mrn'].unique() ) ]
    # filter out records if treatment date is past 2017, the end date of the study period
    df_treat = df_treat.loc[ df_treat['treatment_date'] <= testEndDate ]

    # attach notes to treatment dataframe
    df_treat = combine_feat_to_main_data(
        main=df_treat, feat=mergedNotes, main_date_col='treatment_date', feat_date_col='processed_date', 
        time_window=(-lookbackWin,0)
        )
    df_treat = df_treat.loc[ ~df_treat.note.isna() ]
    df_treat['treatment_date'] = pd.to_datetime( df_treat['treatment_date'] )
    df_treat['maxEPRdate'] = pd.to_datetime( df_treat['maxEPRdate'] )

    # get the change in measurement since previous assessment
    df_treat = get_change_since_prev_session(df_treat)
    
    # extract labels
    if eventName == 'ED_visit':
        df_treat = get_event_labels(df_treat, df_target, event_name='ED_visit', extra_cols=['CTAS_score', 'CEDIS_complaint'])
    else:
        raise Exception("Not implemented yet.")
    
    # remove entries in the data with wrong EPR dates
    df_treat = df_treat.loc[ ( df_treat['maxEPRdate'].dt.year >= 2005 ) & ( df_treat['maxEPRdate'].dt.year <= 2022 ) ]

    # remove records with potential leakage -- EPR date is after the treatment date
    df_treat = df_treat.loc[ pd.to_datetime( df_treat['treatment_date'], utc=True ) > pd.to_datetime( df_treat['maxEPRdate'], utc=True ) ]

    # exclude immediate events
    df_treat = exclude_immediate_events(df_treat, date_cols=['target_ED_visit_date'])

    # save dataframe with anchored note
    df_treat[['mrn','treatment_date','note',f'target_{eventName}']].to_csv( f"{saveDir}/noteAnchored_{eventName}_{configName}.csv" )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataPath", help = "data file path", type = str) # data file path
    parser.add_argument("treatmentDataPath", help = "file path of treatment data", type = str) # treatment data file path
    parser.add_argument("targetDataPath", help = "file path of target data", type = str) # target data file path
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("configName", help = "configuration name", type = str) # configuration name
    parser.add_argument("testEndDate", help = "end date for test period", type = str) # test end date
    parser.add_argument("eventName", help = "name of event", type = str) # event name
    parser.add_argument("lookbackWindow", help = "lookback window for notes to be anchored", type = int) # lookback window
    args = parser.parse_args()

    anchorNoteTreatmentDate( args.dataPath, args.treatmentDataPath, args.targetDataPath,\
                             args.saveDir, args.configName, args.testEndDate,\
                             args.eventName, args.lookbackWindow )
