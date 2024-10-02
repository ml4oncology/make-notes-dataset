import argparse

import numpy as np
import pandas as pd

from .util import process_physician, get_last_updated_missing_ci_notes

def process_missing_notes(data_dir, json_dir, save_dir, mrn_file, file_part_num):
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

    file_name = f"2Blast_part4_{file_part_num}_clinic_notes.csv"
    file_path = data_dir + '/' + file_name

    # print file name
    print(file_path)

    # read data frame
    df = pd.read_csv(file_path)
    df = df.loc[df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: len(x.strip())) > 1].copy()
    
    # add EPR date
    df['epr_date'] = df['ClinicNotes.ClinicNote.date'].fillna(df['ClinicNotes.ClinicNote.effectiveDateTime'])

    # add MRN column
    mrns = pd.read_csv(mrn_file, dtype={'RESEARCH_ID': 'string', 'MRN': 'string'})
    mrn_map = dict(zip(mrns['RESEARCH_ID'], mrns['MRN']))
    df['mrn'] = df['PATIENT_RESEARCH_ID'].map(mrn_map)

    # extract only procedures of interest
    proc_names = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',
                  'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',
                  'Clinic Note (Non-dictated)', 'Discharge Summary',
                  'Unscheduled Discharge Summary', 'Operative Note',
                  'Progress Notes', 'Letters', 'Consultation Report']
    mask = df['ClinicNotes.ClinicNote.code.text'].isin(proc_names)
    df = df[mask].copy()

    # create metadata column
    def split_metadata_col(note_text):
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

    df['meta_data'], df['text_data'] = zip(*df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: split_metadata_col(x)))
    df = df.reset_index()

    # filter out the component_descriptor (metadata) we care about
    notes_meta = ['medical records report', 'note', 'additional details', 'textualreport', 'document more advice',
                  'reason for communication', 'information given', 'reason for call', 'spoke with', 'phone number',
                  'comment', 'communication with', 'person calling', 'e-mail address', 'clinical_note']

    # add clinical_note
    other_meta = ['date dictated', 'dictated by', 'documented by', 'attending/staff', 'report type', 'specialty', 'transcribed by',
                  'family physician', 'department', 'location', 'attending/staff signing off note', 'dictating md verifying note',
                  'dictated by/for', "dictated by and/or verified by/resident's attending"]

    # drop rows which have duplicate values for text_data if meta_data is in other_meta
    df_all_other_meta = df.loc[~df['meta_data'].isin(other_meta)].copy()
    df_physician_meta = df.loc[df['meta_data'].isin(other_meta)].copy()
    df_physician_meta.drop_duplicates(subset=['PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'meta_data', 'text_data'], inplace=True)
    df = pd.concat([df_all_other_meta, df_physician_meta], axis=0)

    # merge text values if the meta_data is the same
    group_by_cols = ['mrn', 'PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'ClinicNotes.ClinicNote.code.text', 'epr_date', 'ClinicNotes.ClinicNote.encounter.reference', 'meta_data']
    df_grouped = df.groupby(group_by_cols).agg(text_data=('text_data', lambda x: '\n'.join(x))).reset_index()
    df_grouped['meta_data'] = df_grouped['meta_data'].str.lower()

    # remove special characters in metadata name to facilitate transition to column names
    map_notes_meta = {elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_') for elem in notes_meta}
    map_other_meta = {elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_').replace("'", '_') for elem in other_meta}

    # retain only metadata of interest
    df_meta_of_interest = df_grouped.loc[df_grouped['meta_data'].isin(notes_meta + other_meta)].copy()

    # map metadata names to facilitate transition to column names upon pivoting
    map_meta = {**map_notes_meta, **map_other_meta}
    df_meta_of_interest['meta_data'] = df_meta_of_interest['meta_data'].map(map_meta)
    cols_to_group_by = [col for col in df_meta_of_interest.columns if col not in ['meta_data', 'text_data']]

    n_patient_obs = df_meta_of_interest[['PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id']].copy().drop_duplicates().shape[0]

    # fill the null values with "dummy" to pivot the dataframe
    df_meta_of_interest[cols_to_group_by] = df_meta_of_interest[cols_to_group_by].fillna(value="dummy")

    # pivot data frame to desired format
    df_meta_of_interest['meta_data'] = df_meta_of_interest['meta_data'].astype(str)
    df_meta_of_interest['text_data'] = df_meta_of_interest['text_data'].astype(str)
    pivot_data_df = df_meta_of_interest.pivot_table('text_data', cols_to_group_by, 'meta_data', aggfunc=lambda x: ' '.join(x))
    pivot_data_df.reset_index(drop=False, inplace=True)
    pivot_data_df = pivot_data_df.rename_axis(None, axis=1)

    # is the shape of the pivoted data frame the same as the number of unique patient-observation pairs?
    if not np.allclose(pivot_data_df.shape[0], n_patient_obs):
        print("check failed")

    # fix Medical Records Report metadata
    mask = (pivot_data_df['medical_records_report'] == 'Medical Records Report') & pivot_data_df['clinical_note'].notna()
    pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']
    mask = pivot_data_df['medical_records_report'].isna() & pivot_data_df['clinical_note'].notna()
    pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']

    # merge all notes into a clinical_notes column
    cols_to_agg_master = ['medical_records_report', 'textualreport', 'note', 'additional_details', 'document_more_advice',
                          'reason_for_communication', 'information_given', 'reason_for_call', 'comment', 'person_calling',
                          'e_mail_address', 'communication_with', 'spoke_with', 'phone_number', 'fax_number', 'relation_to_patient']
    cols_to_agg_local = [x for x in cols_to_agg_master if x in pivot_data_df.columns]
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].astype(str)
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].replace(to_replace='nan', value="")
    pivot_data_df['clinical_notes'] = pivot_data_df[cols_to_agg_local].agg('\n\n'.join, axis=1)
    pivot_data_df.drop(columns=cols_to_agg_local, inplace=True)
    pivot_data_df.drop(columns='clinical_note', inplace=True)

    # apply correction to the date
    pivot_data_df['date_dictated'] = pd.to_datetime(pivot_data_df['date_dictated'], utc=True, format='mixed')
    pivot_data_df['epr_date'] = pd.to_datetime(pivot_data_df['epr_date'], utc=True)
    pivot_data_df['visit_date'] = pivot_data_df['date_dictated'].dt.date
    visit_date_null_mask = pivot_data_df['visit_date'].isna() & pivot_data_df['epr_date'].notna()
    pivot_data_df.loc[visit_date_null_mask, 'visit_date'] = pivot_data_df.loc[visit_date_null_mask, 'epr_date'].dt.date

    # apply correction to the physician name
    pivot_data_df = process_physician(pivot_data_df)

    # extract and merge lastUpdated column
    df_last_updated = get_last_updated_missing_ci_notes(json_dir, file_part_num, proc_names)
    pivot_data_df = pivot_data_df.merge(df_last_updated, how='left', on=['PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id'])

    pivot_data_df = pivot_data_df.loc[pivot_data_df['clinical_notes'] != '\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n'].copy()

    # save extracted data
    pivot_data_df.to_csv(f"{save_dir}/processedMissingClinicalNotes_{file_part_num}.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data-dir", help = "data directory", type = str) # data directory
    parser.add_argument("json-dir", help = "json directory", type = str) # json directory
    parser.add_argument("save-dir", help = "save directory", type = str) # save directory
    parser.add_argument("mrn-file", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("file-part-num", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    process_missing_notes(args.data_dir, args.json_dir, args.save_dir, args.mrn_file, args.file_part_num)
