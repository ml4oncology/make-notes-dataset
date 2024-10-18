import numpy as np
import pandas as pd
import os
import argparse
import logging
from util import (process_date, process_physician, 
                   get_last_updated,
                   get_last_updated_missing_ci_notes)

logger = logging.getLogger(__name__)

def split_metadata_col_missing(note_text):
    """ Split value into meta data and notes data for the missing notes case.
    """
    if '\n' in note_text:
        meta_data = 'clinical_note'
        text_data = note_text
    elif '/' in note_text:
        slash_position = note_text.index('/')
        colon_position = note_text.index(':')
        meta_data = note_text[slash_position + 1:colon_position]
        text_data = note_text[colon_position + 2:]

        if meta_data[0] == '/' or (len(meta_data) > 1 and meta_data[1] == '/'):
            slash_position = meta_data.index('/')
            meta_data = meta_data[slash_position + 1:]
    else:
        meta_data = 'undefined'
        text_data = note_text

    return meta_data, text_data

def create_metadata(df):
    """ Create metadata column for dataframe in the non missing notes case."""

    # Columns to keep in the processed data frame
    columns_to_keep = [
        "mrn",
        "PATIENT_RESEARCH_ID",
        "Observations.ProcCode",
        "Observations.ProcName",
        "observation_id",
        "Observations.StatusFromOrder",
        "occurrence_date_time_from_order",
        "Observations.Observation.basedOn.0.reference",
        "Observations.Observation.encounter.reference",
        "Observations.Observation.status",
        "effective_date_time",
        "meta_data",
        "text_data",
    ]

    # create metadata column called 'meta_data' by merging 2 columns in the raw data frame
    df['meta_data'] = df['component_code_text'].copy()
    df.loc[df['component_code_display'].notnull(), 'meta_data'] =\
          df['component_code_display'].loc[df['component_code_display'].notnull()]
    df['meta_data'] = df['meta_data'].str.lower()
    # clinical notes is split into 2 columns in the raw data frame
    notes_mask = (df['component_extension_url'] == 'NOTES')
    df.loc[notes_mask, 'text_data'] = df['component_extension_value_string'].loc[notes_mask]

    # only keep columns in the processed data frame
    return df[columns_to_keep].copy()

def process_notes(data_dir, json_dir, save_dir, mrn_file, missing_notes, file_part_num):
    """ Process each dataset pulled by the CDI team. 
        
        Restrict to a few procedures only.
        Resulting data frame is a single row for each visit of a patient. 
        Row includes information about the visit (patient MRN, patient code, visit code, 
        attending physician, date, etc) as well as the clinical note for that visit.
        
        Args:
            data_dir: directory path where the raw zip files are saved
            json_dir: directory path where the raw json files are saved
            save_dir: directory path where processed data frame will be saved
            mrn_file: file path for patient code to MRN map
            missing_notes: are these the missing notes after 2018?
            file_part_num: file part number to be processed 
    """

    # generate file name of gzip file
    if missing_notes:
        file_name = f"2Blast_part4_{file_part_num}_clinic_notes.parquet.gzip"
    else:
        file_name = f"2Blast_part4_{file_part_num}_results_with_status_dates.parquet.gzip"

    # print file name
    logger.info(file_name)

    # read parquet.gzip file
    df = pd.read_parquet(os.path.join(data_dir, file_name), engine='pyarrow', use_nullable_dtypes = True)

    # rename certain columns
    if missing_notes:
        new_column_names = {
            'ClinicNotes.ClinicNote.note.text': 'note_text',  
            'ClinicNotes.ClinicNote.date': 'note_date',
            'ClinicNotes.ClinicNote.effectiveDateTime': 'effective_date_time',
            'ClinicNotes.ClinicNote._id': 'clinical_note_id',
            'ClinicNotes.ClinicNote.code.text': 'code_text',
            'ClinicNotes.ClinicNote.encounter.reference': 'encounter_reference'
        }
        proc_name_col = 'code_text'
        visit_id_col = 'clinical_note_id'
    else:
        new_column_names = {
            'Observations.Observation._id': 'observation_id',
            'Observations.OccurrenceDateTimeFromOrder': 'occurrence_date_time_from_order',
            'Observations.Observation.effectiveDateTime': 'effective_date_time',
            'Observations.Observation.component.code.text': 'component_code_text',
            'Observations.Observation.component.code.coding.0.display': 'component_code_display',
            'Observations.Observation.component.extension.2.url': 'component_extension_url',
            'Observations.Observation.component.valueString': 'text_data',
            'Observations.Observation.component.extension.2.valueString': 'component_extension_value_string',
        }
        proc_name_col = 'Observations.ProcName'
        visit_id_col = 'observation_id'

    df = df.rename(columns=new_column_names)

    # if missing, make adjustments to the dataframe
    if missing_notes:
        df = df.loc[df['note_text'].apply(lambda x: len(x.strip())) > 1].copy()
        # add EPR date
        df['epr_date'] = df['note_date'].fillna(df['effective_date_time'])

    # add mrn column
    mrns = pd.read_csv(mrn_file, dtype={'RESEARCH_ID': 'string', 'MRN': 'string'})
    mrn_map = dict(zip(mrns['RESEARCH_ID'], mrns['MRN']))
    df['mrn'] = df['PATIENT_RESEARCH_ID'].map(mrn_map)

    # extract only procedures of interest (if condition if missing)
    PROCEDURE_NAMES_OF_INTEREST = [
        'Letter',
        'Consultation Note',
        'Communication Note',
        'Radiation Therapy Note',
        'OR Procedure/Notes',
        'Clinic Note',
        'Telephone Advice',
        'History & Physical Note',
        'Clinic Note (Non-dictated)',
        'Discharge Summary',
        'Unscheduled Discharge Summary',
        'Operative Note',
        'Progress Notes',
        'Letters',
        'Consultation Report',
    ]
    mask = df[proc_name_col].isin(PROCEDURE_NAMES_OF_INTEREST)
    df = df[mask].copy()    

    # create metadata column
    if missing_notes:
        df['meta_data'], df['text_data'] = zip(*df['note_text'].apply(lambda x: split_metadata_col_missing(x)))
        df = df.reset_index()
    else:
        df = create_metadata(df)

    # filter out the (meta data) we care about
    notes_metadata = [
        'medical records report',
        'note',
        'additional details',
        'textualreport',
        'document more advice',
        'reason for communication',
        'information given',
        'reason for call',
        'spoke with',
        'phone number',
        'comment',
        'communication with',
        'person calling',
        'e-mail address',
        'clinical_note',
    ]

    other_metadata = [
        'date dictated',
        'dictated by',
        'documented by',
        'attending/staff',
        'report type',
        'specialty',
        'transcribed by',
        'family physician',
        'department',
        'location',
        'attending/staff signing off note',
        'dictating md verifying note',
        'dictated by/for',
        "dictated by and/or verified by/resident's attending",
    ]

    # remove special characters in metadata name to facilitate transition to column names
    map_notes_meta = {elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_') for elem in notes_metadata}
    map_other_meta = {elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_').replace("'", '_') for elem in other_metadata}

    # make adjustments if missing notes case
    if missing_notes:
        # drop rows which have duplicate values for text_data if meta data is in other_meta
        df_all_other_meta = df.loc[~df['meta_data'].isin(other_metadata)].copy()
        df_physician_meta = df.loc[df['meta_data'].isin(other_metadata)].copy()
        df_physician_meta.drop_duplicates(subset=['PATIENT_RESEARCH_ID', 'clinical_note_id', 'meta_data', 'text_data'], inplace=True)
        df = pd.concat([df_all_other_meta, df_physician_meta], axis=0)

        # merge text values if the meta_data is the same
        group_by_cols = ['mrn', 'PATIENT_RESEARCH_ID', 'clinical_note_id', 'code_text', 'epr_date', 'encounter_reference', 'meta_data']
        df_grouped = df.groupby(group_by_cols).agg(text_data=('text_data', lambda x: '\n'.join(x))).reset_index()
        df_grouped['meta_data'] = df_grouped['meta_data'].str.lower()
        df = df_grouped.copy()

    # retain only metadata of interest
    df_meta_of_interest = df.loc[df['meta_data'].isin(notes_metadata + other_metadata)].copy()
    if 'Observations.ProcCode' in df_meta_of_interest.columns:
        df_meta_of_interest['Observations.ProcCode'] = df_meta_of_interest['Observations.ProcCode'].astype(int)

    # map metadata names to facilitate transition to column names upon pivoting
    map_meta = {**map_notes_meta, **map_other_meta}
    df_meta_of_interest['meta_data'] = df_meta_of_interest['meta_data'].map(map_meta)
    cols_to_group_by = [col for col in df_meta_of_interest.columns if col not in ['meta_data', 'text_data']]

    # fill the null values with "dummy" to pivot the dataframe
    df_meta_of_interest[cols_to_group_by] = df_meta_of_interest[cols_to_group_by].fillna(value="dummy")

    # pivot data frame to desired format
    df_meta_of_interest['meta_data'] = df_meta_of_interest['meta_data'].astype(str)
    df_meta_of_interest['text_data'] = df_meta_of_interest['text_data'].astype(str)
    pivot_data_df = df_meta_of_interest.pivot_table('text_data', cols_to_group_by, 'meta_data', aggfunc=lambda x: ' '.join(x))
    pivot_data_df.reset_index(drop=False, inplace=True)
    pivot_data_df = pivot_data_df.rename_axis(None, axis=1)

    # count the number of patients
    n_patient_obs = df_meta_of_interest[['PATIENT_RESEARCH_ID', visit_id_col]].copy().drop_duplicates().shape[0]
    assert np.allclose(pivot_data_df.shape[0], n_patient_obs), "Number of observations does not match number of patients"

    # if missing, fix Medical Records Report meta data
    if missing_notes:
        mask = (pivot_data_df['medical_records_report'] == 'Medical Records Report') & pivot_data_df['clinical_note'].notna()
        pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']
        mask = pivot_data_df['medical_records_report'].isna() & pivot_data_df['clinical_note'].notna()
        pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']

    # merge all notes into a clinical_notes column
    cols_to_agg_master = ['medical_records_report', 'textualreport', 'note', 'additional_details', 
                          'document_more_advice', 'reason_for_communication', 'information_given', 
                          'reason_for_call', 'comment', 'person_calling', 'e_mail_address', 
                          'communication_with', 'spoke_with', 'phone_number', 'fax_number', 
                          'relation_to_patient']
    cols_to_agg_local = [x for x in cols_to_agg_master if x in pivot_data_df.columns]
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].astype(str)
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].replace(to_replace='nan', value="")
    pivot_data_df['clinical_notes'] = pivot_data_df[cols_to_agg_local].agg('\n\n'.join, axis=1)
    pivot_data_df.drop(columns=cols_to_agg_local, inplace=True)
    if 'clinical_note' in pivot_data_df.columns: 
        pivot_data_df.drop(columns='clinical_note', inplace=True)

    # apply correction to the date 
    if missing_notes:
        pivot_data_df['date_dictated'] = pd.to_datetime(pivot_data_df['date_dictated'], utc=True, format='mixed')
        pivot_data_df['epr_date'] = pd.to_datetime(pivot_data_df['epr_date'], utc=True)
        pivot_data_df['visit_date'] = pivot_data_df['date_dictated'].dt.date
        visit_date_null_mask = pivot_data_df['visit_date'].isna() & pivot_data_df['epr_date'].notna()
        pivot_data_df.loc[visit_date_null_mask, 'visit_date'] = pivot_data_df.loc[visit_date_null_mask, 'epr_date'].dt.date
    else:
        pivot_data_df = process_date(pivot_data_df)
    
    # apply correction to the physician name
    pivot_data_df = process_physician(pivot_data_df)

    # extract and merge last_updated column
    if missing_notes:
        df_last_updated = get_last_updated_missing_ci_notes(json_dir, file_part_num, PROCEDURE_NAMES_OF_INTEREST)
    else:
        df_last_updated = get_last_updated(json_dir, file_part_num, PROCEDURE_NAMES_OF_INTEREST)
    pivot_data_df = pivot_data_df.merge(df_last_updated, how='left', on=['PATIENT_RESEARCH_ID', visit_id_col])

    pivot_data_df = pivot_data_df.loc[pivot_data_df['clinical_notes'] != '\n'*len(cols_to_agg_master)].copy()

    # save extracted data
    if missing_notes:
        pivot_data_df.to_parquet(f"{save_dir}/processed_missing_clinical_notes_{file_part_num}.parquet.gzip", compression='gzip', index=False)
    else:
        pivot_data_df.to_parquet(f"{save_dir}/processed_clinical_notes_{file_part_num}.parquet.gzip", compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help="data directory", type=str)  # data directory
    parser.add_argument("json_dir", help = "json directory", type = str) # json directory
    parser.add_argument("save_dir", help = "save directory", type = str) # save directory
    parser.add_argument("mrn_file", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("missing_notes", help = "MRN missing notes", type = int) # missing notes after 2017
    parser.add_argument("file_part_num", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    process_notes(args.data_dir, args.json_dir, args.save_dir, 
                  args.mrn_file, args.missing_notes, args.file_part_num)