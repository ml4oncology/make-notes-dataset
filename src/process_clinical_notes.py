import numpy as np
import pandas as pd
import os
import argparse
import logging
from .util import process_date, process_physician, get_last_updated

logger = logging.getLogger(__name__)

def process_clinical_notes(data_dir, json_dir, save_dir, mrn_file, file_part_num):
    """Process each dataset pulled by the CDI team. 
    
    Restrict to a few procedures only.
    Resulting data frame is a single row for each visit of a patient. 
    Row includes information about the visit (patient MRN, patient code, visit code, attending physician, date, etc)
    as well as the clinical note for that visit.

    Args:
        data_dir: directory path where the raw zip files are saved
        json_dir: directory path where the raw json files are saved
        save_dir: directory path where processed data frame will be saved
        mrn_file: file path for patient code to MRN map
        file_part_num: file part number to be processed
    """

    file_name = f"2Blast_part4_{file_part_num}_results_with_status_dates-output.zip"
    file_path = data_dir + '/' + file_name

    # unzip file
    csv_file_path = data_dir + '/' + f"2Blast_part4_{file_part_num}_results_with_status_dates.csv"
    if not os.path.isfile(csv_file_path):
        os.system(f"unzip {file_path} -d {data_dir}")

    # read data frame
    df = pd.read_csv(csv_file_path)

    # extract only procedures of interest
    proc_names = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',
                  'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',
                  'Clinic Note (Non-dictated)', 'Discharge Summary',
                  'Unscheduled Discharge Summary', 'Operative Note',
                  'Progress Notes', 'Letters', 'Consultation Report']
    mask = df['Observations.ProcName'].isin(proc_names)
    df = df[mask].copy()

    # create metadata column called 'component_descriptor' by merging 2 columns in raw dataframe
    df['component_descriptor'] = df['Observations.Observation.component.code.text'].copy()
    df.loc[df['Observations.Observation.component.code.coding.0.display'].notnull(), 'component_descriptor'] = \
        df['Observations.Observation.component.code.coding.0.display'].loc[df['Observations.Observation.component.code.coding.0.display'].notnull()]
    df['component_descriptor'] = df['component_descriptor'].str.lower()

    # clinical notes is split into 2 columns in raw dataframe
    notes_mask = (df['Observations.Observation.component.extension.2.url'] == 'NOTES')
    df.loc[notes_mask, 'Observations.Observation.component.valueString'] = df['Observations.Observation.component.extension.2.valueString'].loc[notes_mask]
    
    # add MRN column
    df_mrn = pd.read_csv(mrn_file, dtype={'RESEARCH_ID': 'string', 'MRN': 'string'})
    mrn_map = dict(zip(df_mrn['RESEARCH_ID'], df_mrn['MRN']))
    df['MRN'] = df['PATIENT_RESEARCH_ID'].map(mrn_map)

    # columns to keep
    cols_to_keep = ['MRN', 'PATIENT_RESEARCH_ID', 'Observations.ProcCode', 'Observations.ProcName', 'Observations.Observation._id',\
              'Observations.StatusFromOrder', 'Observations.OccurrenceDateTimeFromOrder', 'Observations.Observation.basedOn.0.reference',\
                'Observations.Observation.encounter.reference' , 'Observations.Observation.status', \
                   'Observations.Observation.effectiveDateTime', 'component_descriptor', 'Observations.Observation.component.valueString']

    # filter out the component_descriptor (metadata) we care about
    notes_meta = ['medical records report', 'note', 'additional details', 'textualreport', 'document more advice',\
                'reason for communication', 'information given', 'reason for call', 'spoke with', 'phone number', \
                    'comment', 'communication with', 'person calling', 'e-mail address']

    other_meta = ['date dictated', 'dictated by', 'documented by', 'attending/staff', 'report type', 'specialty', 'transcribed by', \
                'family physician', 'department', 'location', 'attending/staff signing off note', 'dictating md verifying note',\
                'dictated by/for', "dictated by and/or verified by/resident's attending"]

    # remove special characters in metadata name to facilitate transition to column names
    map_notes_meta = {}
    for elem in notes_meta:
        map_notes_meta[elem] = elem.replace(' ', '_').replace('-', '_').replace('/', '_')

    map_other_meta = {}
    for elem in other_meta:
        map_other_meta[elem] = elem.replace(' ', '_').replace('-', '_').replace('/', '_').replace("'", '_')

    # retain only metadata of interest
    df_meta_of_interest = df.loc[df['component_descriptor'].isin(notes_meta + other_meta), cols_to_keep].copy()
    df_meta_of_interest['Observations.ProcCode'] = df_meta_of_interest['Observations.ProcCode'].astype(int)

    ################## do some checks
    ################## print file part number
    print(f"Part number is {file_part_num}")

    ################## count how many unique patient-observation id pairs there are
    n_patient_obs = df_meta_of_interest[['PATIENT_RESEARCH_ID', 'Observations.Observation._id']].copy().drop_duplicates().shape[0]
    
    # map metadata names to facilitate transition to column names upon pivoting
    map_meta = map_notes_meta | map_other_meta
    df_meta_of_interest['component_descriptor'] = df_meta_of_interest['component_descriptor'].map(map_meta)
    cols_to_group_by = [col for col in cols_to_keep if col not in ['component_descriptor', 'Observations.Observation.component.valueString']]

    # fill the null values with "dummy" to pivot the dataframe
    df_meta_of_interest[cols_to_group_by] = df_meta_of_interest[cols_to_group_by].fillna(value="dummy")

    # pivot data frame to desired format
    df_meta_of_interest['Observations.Observation.component.valueString'] = df_meta_of_interest['Observations.Observation.component.valueString'].astype(str)
    df_meta_of_interest['component_descriptor'] = df_meta_of_interest['component_descriptor'].astype(str)
    pivot_data_df = df_meta_of_interest.pivot_table('Observations.Observation.component.valueString', cols_to_group_by, 'component_descriptor', aggfunc=lambda x: ' '.join(x))
    pivot_data_df.reset_index(drop=False, inplace=True)
    pivot_data_df = pivot_data_df.rename_axis(None, axis=1)

    ################## is the shape of the pivoted data frame the same as the number of unique patient-observation pairs?
    if not np.allclose(pivot_data_df.shape[0], n_patient_obs):
        print("check failed")

    # merge all notes into a clinical_notes column
    cols_to_agg_master = ['medical_records_report', 'textualreport', 'note', 'additional_details', 'document_more_advice',\
             'reason_for_communication', 'information_given', 'reason_for_call', 'comment', 'person_calling',\
             'e_mail_address', 'communication_with', 'spoke_with', 'phone_number', 'fax_number', 'relation_to_patient']
    cols_to_agg_local = [x for x in cols_to_agg_master if x in pivot_data_df.columns]
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].astype(str)
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].replace(to_replace='nan', value="")
    pivot_data_df['clinical_notes'] = pivot_data_df[cols_to_agg_local].agg('\n\n'.join, axis=1)
    pivot_data_df.drop(columns=cols_to_agg_local, inplace=True)

    # apply correction to the date
    pivot_data_df = process_date(pivot_data_df)
    
    # apply correction to the physician name
    pivot_data_df = process_physician(pivot_data_df)

    # extract and merge last_updated column
    df_last_updated = get_last_updated(json_dir, file_part_num, proc_names)
    pivot_data_df = pivot_data_df.merge(df_last_updated, how='left', on=['PATIENT_RESEARCH_ID', 'Observations.Observation._id'])

    # save extracted data
    pivot_data_df.to_csv(f"{save_dir}/processed_clinical_notes_{file_part_num}.csv")

    # delete csv files
    os.system(f"rm {data_dir}/2Blast_part4_{file_part_num}_results_with_status_dates.csv")
    os.system(f"rm {data_dir}/2Blast_part4_{file_part_num}_results_with_status_dates-meta.csv")
    os.system(f"rm {data_dir}/2Blast_part4_{file_part_num}_results_with_status_dates-msgs.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help="data directory", type=str)  # data directory
    parser.add_argument("json_dir", help = "json directory", type = str) # json directory
    parser.add_argument("save_dir", help = "save directory", type = str) # save directory
    parser.add_argument("mrn_file", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("file_part_num", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    process_clinical_notes(args.data_dir, args.json_dir, args.save_dir, args.mrn_file, args.file_part_num)
