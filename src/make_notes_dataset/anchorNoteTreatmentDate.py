import numpy as np
import pandas as pd
import argparse
from pathlib import Path
import sys
ROOT_DIR = Path(__file__).parent.parent.parent.as_posix()
sys.path.append(ROOT_DIR)
from common.src.anchor import combine_feat_to_main_data
from common.src.engineer import (get_change_since_prev_session,
                                 get_missingness_features,
                                 collapse_rare_categories)
from common.src.filter import (drop_samples_with_no_targets, 
                               drop_unused_drug_features, 
                               drop_highly_missing_features)
from common.src.constants import SYMP_COLS
from preduce import (get_event_labels, exclude_immediate_events, 
                     get_symptom_labels, convert_to_binary_symptom_labels, 
                     indicate_immediate_events, fill_missing_data,
                     keep_only_one_per_week)

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/constants")
# load constants from file
from constants import aliasDictionary

def anchorNoteTreatmentDate(dataPath, treatmentDataPath, EDVisitDataDir,
                            symptomDataDir, lastSeenDataDir,
                            saveDir, configName,
                            testEndDate, lookbackWin):
    """
        Anchor the note to treatment date depending on specified configuration.
        Generate train, validation, test split.

        dataPath: file path of the notes data
        treatmentDataPath: file path of the treatment data frame
        EDVisitDataDir: directory of the ED visit data frame
        symptomDataDir: directory of the symptom data frame
        lastSeenDataDir: directory of the last seen data frame
        saveDir: directory path where processed data frame will be saved
        configName: configuration name for how to anchor note to treatment date
        testEndDate: ending date for the test time period (and end date of the study period)
        lookbackWin: lookback window for the notes to be anchored to treatment date
    """

    # load notes file
    mergedNotes = pd.read_parquet(f'{dataPath}', engine='pyarrow', use_nullable_dtypes = True)

    # load treatment-centered data frame
    df_treat = pd.read_parquet(f'{treatmentDataPath}', engine='pyarrow', use_nullable_dtypes = True)

    if configName in ['mostRecentVisit-medOnc-ConsultLetterClinic', 'mostRecentVisit-appendFirst-medOnc-ConsultLetterClinic', 'firstVisitOnly-medOnc-ConsultLetterClinic'] :
        # only consider notes written by a medical oncologist 
        # only consider consultation, letter, clinic notes
        medOncs = list(set(aliasDictionary.values()))
        procName = ['Clinic Note', 'Letter', 'History & Physical Note', 'Consultation Note']
        mergedNotes = mergedNotes.loc[ (mergedNotes['processed_physician_name'].isin( medOncs )) &\
                                       (mergedNotes['Observations.ProcName'].isin( procName )) ].copy()
        
        # merge records of patient on the same day
        # take the maximum of the EPR dates

        mergedNotes['note'] = mergedNotes['Observations.ProcName'] + ':\n' + mergedNotes['clinical_notes']
        # mergedNotes = mergedNotes.groupby(['MRN','processed_date']).agg(
        #                 processed_note=('note', lambda x: '\n'.join(x)),
        #                 maxEPRdate=('EPRDate', 'max')).reset_index()
        # add physician name and note type for statistics tracking
        mergedNotes = mergedNotes.groupby(['MRN','processed_date']).agg(
                        processed_note=('note', lambda x: '\n'.join(x)),
                        maxEPRdate=('EPRDate', 'max'),
                        stats_physician=('processed_physician_name','unique'),
                        stats_noteType=('Observations.ProcName','unique')).reset_index()
        mergedNotes.rename(columns={"MRN": "mrn", "processed_note": "note"}, inplace=True)
        mergedNotes['processed_date'] = mergedNotes['processed_date'].dt.date
        mergedNotes['processed_date'] = mergedNotes['processed_date'].astype('<M8[ns]')

        if configName == 'mostRecentVisit-appendFirst-medOnc-ConsultLetterClinic':
            # get the first note
            mergedNotes.sort_values(by='processed_date', inplace=True)
            firstNote = mergedNotes.groupby(['mrn'])['note'].first().reset_index(name='first_note')
            # append the first note
            mergedNotes = mergedNotes.merge(firstNote, on="mrn")
            mergedNotes['appended_first_note'] = mergedNotes.apply( lambda x: x['note'] if x['note'] == x['first_note'] else x['first_note'] + '\n' + x['note'], axis = 1  )
            # retain only columns of interest
            mergedNotes = mergedNotes[['mrn','processed_date','maxEPRdate','appended_first_note','stats_physician','stats_noteType']]
            mergedNotes.rename(columns={"appended_first_note": "note"}, inplace=True)
        
        elif configName == 'firstVisitOnly-medOnc-ConsultLetterClinic':
            # keep only the first note
            mergedNotes.sort_values(by='processed_date', inplace=True)
            mergedNotes = mergedNotes.groupby('mrn')[['maxEPRdate','processed_date','note','stats_physician','stats_noteType']].first().reset_index()

    else:
        raise Exception("Not implemented yet.")
    
    # filter the treatment-centered data frame
    df_treat = df_treat.loc[ df_treat['mrn'].isin( mergedNotes['mrn'].unique() ) ]
    # filter out records if treatment date is past 2017, the end date of the study period
    # note: there is no need to cap the data at the start date since the notes data set
    # only contains data starting from the start date. if no notes are anchored to treatment 
    # data, they will be dropped
    df_treat = df_treat.loc[ df_treat['treatment_date'] <= testEndDate ]

    # keep only the first treatment session of a given week
    df_treat = keep_only_one_per_week(df_treat)

    # attach notes to treatment dataframe
    df_treat = combine_feat_to_main_data(
        main=df_treat, feat=mergedNotes, main_date_col='treatment_date', feat_date_col='processed_date', 
        time_window=(-lookbackWin,0)
        )
    
    df_treat['treatment_date'] = pd.to_datetime( df_treat['treatment_date'] )
    df_treat['maxEPRdate'] = pd.to_datetime( df_treat['maxEPRdate'] )

    # get the change in measurement since previous assessment
    df_treat = get_change_since_prev_session(df_treat)
    
    # consider all events
    # process ED_visit
    # load ed target data frame
    df_target_ed = pd.read_parquet(f'{EDVisitDataDir}/emergency_room_visit.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)
    df_treat = get_event_labels(df_treat, df_target_ed, event_name='ED_visit', extra_cols=['CTAS_score', 'CEDIS_complaint'])
    
    # exclude immediate events
    df_treat = exclude_immediate_events(df_treat, date_cols=['target_ED_visit_date'])

    # process symptom targets
    target_pt_increases = [1, 3]
    # load symp target data frame
    df_target_symp = pd.read_parquet(f'{symptomDataDir}/symptom.parquet.gzip')
    df_treat = get_symptom_labels(df_treat, df_target_symp)
    for pt_increase in target_pt_increases:
        scoring_map = {symp: pt_increase for symp in SYMP_COLS}
        df_treat = convert_to_binary_symptom_labels(df_treat, scoring_map=scoring_map)

    # exclude immediate events
    date_cols = [f'target_{symp}_survey_date' for symp in SYMP_COLS]
    for pt in target_pt_increases:
        targ_cols = [f'target_{symp}_{pt}pt_change' for symp in SYMP_COLS]
        df_treat = indicate_immediate_events(df_treat, targ_cols, date_cols)
 
    # process death
    df_treat['target_death_in_365d'] =  df_treat['date_of_death'] < df_treat['treatment_date'] + pd.Timedelta(days=365)
    df_treat['target_death_in_30d'] = df_treat['date_of_death'] < df_treat['treatment_date'] + pd.Timedelta(days=30)

    last_seen_date = pd.read_parquet(f'{lastSeenDataDir}/last_seen_dates.parquet.gzip')
    df_treat['last_seen_date'] = df_treat['mrn'].map(last_seen_date['last_seen_date'])
    mask = df_treat['last_seen_date'] > df_treat['date_of_death']

    df_treat[['target_death_in_365d', 'target_death_in_30d']] = df_treat[['target_death_in_365d', 'target_death_in_30d']].astype(int)
    df_treat.loc[mask, ['target_death_in_365d', 'target_death_in_30d']] = -1
        
    # drop rows that don't have any note data
    df_treat = df_treat.loc[ ~df_treat.note.isna() ]

    # remove entries in the data with wrong EPR dates
    df_treat = df_treat.loc[ ( df_treat['maxEPRdate'].dt.year >= 2005 ) & ( df_treat['maxEPRdate'].dt.year <= 2022 ) ]

    # remove records with potential leakage -- EPR date is after the treatment date
    df_treat = df_treat.loc[ pd.to_datetime( df_treat['treatment_date'], utc=True ) > pd.to_datetime( df_treat['maxEPRdate'], utc=True ) ]

    cols = df_treat.columns
    # drop rows where all targets are unavailable
    keep_cols = cols[cols.str.contains('target') & ~cols.str.contains('date')].tolist()
    exclude_cols = [f'target_{col}' for col in SYMP_COLS] + [f'target_{col}_change' for col in SYMP_COLS] + ['target_CTAS_score', 'target_CEDIS_complaint']
    target_cols = [col for col in keep_cols if col not in exclude_cols]
    df_treat.loc[:, target_cols].fillna(value=-1, inplace=True)
    df_treat[ target_cols ] = df_treat[ target_cols ].astype(int)
    df_treat = drop_samples_with_no_targets(df_treat, target_cols, missing_val=-1) 

    # drop drug features that were never used
    df_treat = drop_unused_drug_features(df_treat)

    # fill missing data that can be filled heuristically
    df_treat = fill_missing_data(df_treat)

    # drop features with high missingness
    keep_cols = df_treat.columns[df_treat.columns.str.contains('target_')]
    df_treat = drop_highly_missing_features(df_treat, missing_thresh=80, keep_cols=keep_cols)

    # create missingness features
    df_treat = get_missingness_features(df_treat)

    # collapse rare morphology and cancer sites into 'Other' category
    df_treat = collapse_rare_categories(df_treat, catcols=['cancer_site', 'morphology'])

    # save dataframe with anchored note
    cols = df_treat.columns
    cols_no_target = [col for col in cols if 'target' not in col]

    df_treat[cols_no_target + target_cols].to_csv( f"{saveDir}/noteAnchored_{configName}.csv" )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataPath", help = "data file path", type = str) # data file path
    parser.add_argument("treatmentDataPath", help = "file path of treatment data", type = str) # treatment data file path
    parser.add_argument("EDVisitDataDir", help = "directory of ED visit data", type = str) # directory of ED visit data
    parser.add_argument("symptomDataDir", help = "directory of symptom data", type = str) # directory of symptom data
    parser.add_argument("lastSeenDataDir", help = "directory of last seen data", type = str) # directory of last seen data
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("configName", help = "configuration name", type = str) # configuration name
    parser.add_argument("testEndDate", help = "end date for test period", type = str) # test end date
    parser.add_argument("lookbackWindow", help = "lookback window for notes to be anchored", type = int) # lookback window
    args = parser.parse_args()

    anchorNoteTreatmentDate( args.dataPath, args.treatmentDataPath, args.EDVisitDataDir,
                             args.symptomDataDir, args.lastSeenDataDir,
                             args.saveDir, args.configName, args.testEndDate,
                             args.lookbackWindow )



# # filter out dates before 2014 and after 2020
# df = drop_samples_outside_study_date(df)
# # symptom
# df = drop_samples_outside_study_date(df)
# get the change in measurement since previous assessment
# df = get_change_since_prev_session(df)
# get the change in measurement since previous assessment
# df = get_change_since_prev_session(df)
# extract labels
# df = get_event_labels(df, emerg, event_name='ED_visit', extra_cols=['CTAS_score', 'CEDIS_complaint'])
# extract labels
# symp = pd.read_parquet('./data/external/symptom.parquet.gzip')
# df = get_symptom_labels(df, symp)
# for pt_increase in target_pt_increases:
#     scoring_map = {symp: pt_increase for symp in SYMP_COLS}
#     df = convert_to_binary_symptom_labels(df, scoring_map=scoring_map)
# keep only the first treatment session of a given week
# df = keep_only_one_per_week(df)
# ED visit
# filter out sessions without any labels
# target_cols = 'target_' + pd.Index(SYMP_CHANGE_COLS)
# df = drop_samples_with_no_targets(df, target_cols)
# drop drug features that were never used
# df = drop_unused_drug_features(df)
# fill missing data that can be filled heuristically
# df = fill_missing_data(df)
# drop features with high missingness
# keep_cols = df.columns[df.columns.str.contains('target_')]
# df = drop_highly_missing_features(df, missing_thresh=75, keep_cols=keep_cols)
# create missingness features
# df = get_missingness_features(df)
# collapse rare morphology and cancer sites into 'Other' category
# df = collapse_rare_categories(df, catcols=['cancer_site', 'morphology'])