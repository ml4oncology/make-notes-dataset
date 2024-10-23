import numpy as np
import pandas as pd
import argparse
from pathlib import Path
import sys
import re
ROOT_DIR = Path(__file__).parent.parent.parent.as_posix()
sys.path.append(ROOT_DIR)
from preduce import keep_only_one_per_week

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/constants")
# load constants from file
from constants import aliasDictionary

def genRollingNote(dataPath, treatmentDataPath, saveDir, testEndDate):
    """
        Generate rolling note over patient history anchored on treatment date.

        dataPath: file path of the notes data
        treatmentDataPath: file path of the treatment data frame
        saveDir: directory path where processed data frame will be saved
        testEndDate: ending date for the test time period (and end date of the study period)
    """

    # load notes file
    mergedNotes = pd.read_parquet(f'{dataPath}', engine='pyarrow', use_nullable_dtypes = True)
    # load treatment-centered data frame
    df_treat = pd.read_parquet(f'{treatmentDataPath}', engine='pyarrow', use_nullable_dtypes = True)

    # restrict note type
    procName = ['Clinic Note', 'Letter', 'History & Physical Note', 'Consultation Note']
    mergedNotes = mergedNotes.loc[ (mergedNotes['Observations.ProcName'].isin( procName )) ].copy()
    mergedNotes['note'] = mergedNotes['Observations.ProcName'] + ':\n' + mergedNotes['clinical_notes']

    df_treat = df_treat.loc[ df_treat['mrn'].isin( mergedNotes['MRN'].unique() ) ]
    df_treat = df_treat.loc[ df_treat['treatment_date'] <= testEndDate ]
    df_treat = keep_only_one_per_week(df_treat)

    # exclude MRNs with long notes
    mrn_exclude = ['2495421', '3701975', '3828698', '3846167', '3925862', '3956075']
    df_treat = df_treat.loc[~df_treat['mrn'].isin(mrn_exclude)]

    # strip unnecessary lines from notes
    mergedNotes['note'] = mergedNotes['note'].apply(lambda x: x.rstrip("\n").replace("\n\n", "\n"))
    mergedNotes["note"] = mergedNotes["note"].apply(lambda x: re.sub(r"[\n]+", "\n", x))

    # loop over each mrn
    unique_mrn = df_treat['mrn'].unique().tolist()
    mrn_list = []
    trt_date_list = []
    concat_list = []
    for mrn_val in unique_mrn:
        # get notes for a mrn and organize by date
        df_merged_temp = mergedNotes.loc[mergedNotes['MRN'] == mrn_val]
        df_merged_temp = df_merged_temp.sort_values(by='processed_date')
        df_treat_temp = df_treat.loc[df_treat['mrn'] == mrn_val,['treatment_date']]
        df_treat_temp = df_treat_temp.sort_values(by='treatment_date')
        # loop over treatment dates
        treat_dates = df_treat_temp['treatment_date'].tolist()
        for treat_val in treat_dates:
            # find notes where date is before treatment date and EPR date is before treatment date
            df_merged_trt_temp = df_merged_temp.loc[ pd.to_datetime(df_merged_temp['processed_date'], utc=True) <= pd.to_datetime(treat_val, utc=True) ]
            df_merged_trt_temp = df_merged_trt_temp.loc[ pd.to_datetime(df_merged_trt_temp['EPRDate'], utc=True) < pd.to_datetime(treat_val, utc=True) ]
            concat_notes = '\n\n'.join(df_merged_trt_temp['note'].astype(str))

            mrn_list.append(mrn_val)
            trt_date_list.append(treat_val)
            concat_list.append(concat_notes)
    df_rolling_note = pd.DataFrame({"mrn":mrn_list, "treatment_date":trt_date_list, "rolling_note": concat_list})
    df_rolling_note.to_parquet(f'{saveDir}/rolling_note.parquet.gzip', compression='gzip', index=False)

    # try with de-identified
    # try reversing the order of notes

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataPath", help = "data file path", type = str) # data file path
    parser.add_argument("treatmentDataPath", help = "file path of treatment data", type = str) # treatment data file path
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("testEndDate", help = "end date for test period", type = str) # test end date
    args = parser.parse_args()

    genRollingNote(args.dataPath, args.treatmentDataPath, 
                             args.saveDir, args.testEndDate)
