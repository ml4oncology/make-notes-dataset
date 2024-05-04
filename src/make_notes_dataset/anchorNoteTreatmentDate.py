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
from preduce import get_change_since_prev_session, get_event_labels, exclude_immediate_events, get_symptom_labels, convert_to_binary_symptom_labels, drop_samples_with_no_targets, indicate_immediate_events, get_death

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/constants")
# load constants from file
from constants import aliasDictionary

def anchorNoteTreatmentDate(dataPath, treatmentDataPath, targetDataDir, saveDir, configName,\
                            testEndDate, lookbackWin):
    """
        Anchor the note to treatment date depending on specified configuration.
        Generate train, validation, test split.

        dataPath: file path of the notes data
        treatmentDataPath: file path of the treatment data frame
        targetDataPath: file path of the target data frame
        saveDir: directory path where processed data frame will be saved
        configName: configuration name for how to anchor note to treatment date
        testEndDate: ending date for the test time period (and end date of the study period)
        lookbackWin: lookback window for the notes to be anchored to treatment date
    """

    symp_cols = [
    'esas_pain',
    'esas_tiredness',
    'esas_nausea',
    'esas_depression',
    'esas_anxiety',
    'esas_drowsiness',
    'esas_appetite',
    'esas_well_being',
    'esas_shortness_of_breath',
    ]

    # load notes file
    mergedNotes = pd.read_parquet(f'{dataPath}', engine='pyarrow', use_nullable_dtypes = True)

    # load treatment-centered data frame
    df_treat = pd.read_parquet(f'{treatmentDataPath}', engine='pyarrow', use_nullable_dtypes = True)

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
    
    # consider all events
    # process ED_visit
    # load ed target data frame
    df_target_ed = pd.read_parquet(f'{targetDataDir}/emergency_room_visit.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)
    df_treat = get_event_labels(df_treat, df_target_ed, event_name='ED_visit', extra_cols=['CTAS_score', 'CEDIS_complaint'])
    
    # exclude immediate events
    df_treat = exclude_immediate_events(df_treat, date_cols=['target_ED_visit_date'])

    # process symptom targets
    target_pt_increases = [1, 3]
    # load symp target data frame
    df_target_symp = pd.read_parquet(f'{targetDataDir}/symptom.parquet.gzip')
    df_treat = get_symptom_labels(df_treat, df_target_symp)
    for pt_increase in target_pt_increases:
        scoring_map = {symp: pt_increase for symp in symp_cols if symp != 'patient_ecog'}
        df_treat = convert_to_binary_symptom_labels(df_treat, scoring_map=scoring_map)

    # exclude immediate events
    date_cols = [f'target_{symp}_survey_date' for symp in symp_cols]
    for pt in target_pt_increases:
        targ_cols = [f'target_{symp}_{pt}pt_change' for symp in symp_cols]
        df_treat = indicate_immediate_events(df_treat, targ_cols, date_cols)
 
    # process death
    df_target_death = pd.read_parquet(f'{targetDataDir}/death_dates.parquet.gzip')
    death_map = dict(get_death(df_target_death))
    df_treat['death_date1'] = df_treat['mrn'].map(death_map)

    canc_reg = pd.read_parquet(f'{targetDataDir}/cancer_registry.parquet.gzip')
    death_map2 = dict(get_death(canc_reg))
    df_treat['death_date2'] = df_treat['mrn'].map(death_map2)

    df_treat['death_date'] = df_treat[['death_date1', 'death_date2']].min(axis=1)
    df_treat['death_in_365d'] =  df_treat['death_date'] < df_treat['treatment_date'] + pd.Timedelta(days=365)
    df_treat['death_in_30d'] = df_treat['death_date'] < df_treat['treatment_date'] + pd.Timedelta(days=30)

    last_seen_date = pd.read_parquet(f'{targetDataDir}/last_seen_dates.parquet.gzip')
    df_treat['last_seen_date'] = df_treat['mrn'].map(last_seen_date['last_seen_date'])
    mask = df_treat['last_seen_date'] > df_treat['death_date']

    df_treat[['death_in_365d', 'death_in_30d']] = df_treat[['death_in_365d', 'death_in_30d']].astype(int)
    df_treat.loc[mask, ['death_in_365d', 'death_in_30d']] = -1
        
    # remove entries in the data with wrong EPR dates
    df_treat = df_treat.loc[ ( df_treat['maxEPRdate'].dt.year >= 2005 ) & ( df_treat['maxEPRdate'].dt.year <= 2022 ) ]

    # remove records with potential leakage -- EPR date is after the treatment date
    df_treat = df_treat.loc[ pd.to_datetime( df_treat['treatment_date'], utc=True ) > pd.to_datetime( df_treat['maxEPRdate'], utc=True ) ]

    keep_cols = list( df_treat.columns[df_treat.columns.str.contains('target_')] )
    df_treat.loc[ df_treat[keep_cols].isnull(), keep_cols ] = -1
    df_treat[ keep_cols ] = df_treat[ keep_cols ].astype(int)
    df_treat = drop_samples_with_no_targets(df_treat, keep_cols, missing_val=-1) 

    # save dataframe with anchored note
    df_treat[['mrn','treatment_date','note'] + keep_cols].to_csv( f"{saveDir}/noteAnchored_{configName}.csv" )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataPath", help = "data file path", type = str) # data file path
    parser.add_argument("treatmentDataPath", help = "file path of treatment data", type = str) # treatment data file path
    parser.add_argument("targetDataDir", help = "directory of target data", type = str) # directory of target data
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("configName", help = "configuration name", type = str) # configuration name
    parser.add_argument("testEndDate", help = "end date for test period", type = str) # test end date
    parser.add_argument("lookbackWindow", help = "lookback window for notes to be anchored", type = int) # lookback window
    args = parser.parse_args()

    anchorNoteTreatmentDate( args.dataPath, args.treatmentDataPath, args.targetDataDir,\
                             args.saveDir, args.configName, args.testEndDate,\
                             args.lookbackWindow )
