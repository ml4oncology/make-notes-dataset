import sys
import numpy as np
import pandas as pd
import os
import argparse
import logging
import re
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
from util import (process_date, process_physician, 
                   get_last_updated,
                   get_last_updated_clinic_ci_notes,
                   extract_header)
# sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/HealthReportRecords/constants")
sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/info")

# load constants from file
# from constants import ambigousPhysicians, aliasDictionary
from phys_names import ambigousPhysicians, aliasDictionary

logger = logging.getLogger(__name__)

def remove_bmk_lines(text):
    text = text.rstrip()
    lines = text.splitlines()

    # Remove first line if it's just 'bmk' (with optional whitespace)
    if lines and lines[0].strip() == 'bmk':
        lines = lines[1:]

    # Remove last line if it's just 'bmk' (with optional whitespace)
    if lines and lines[-1].strip() == 'bmk':
        lines = lines[:-1]

    # Strip leading/trailing spaces from non-blank lines
    processed_lines = [
        line.strip() if line.strip() else line
        for line in lines
    ]

    return '\n'.join(processed_lines)
def split_metadata_col_clinic(note_text):
    """ Split value into meta data and notes data for the clinic notes case.
    The expected format is of the form 10060/Report Type: Clinic Note.
    However, if the content is a clinic note, the content of the cell is just the
    note. It deviates from this format. This is handled by the if statement below.
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
        # to be honest, not sure what is happening in this case

    return meta_data, text_data

def create_metadata(df):
    """ Create metadata column for dataframe in the observation notes case."""

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

def process_notes(data_dir, json_dir, save_dir, mrn_file, clinic_notes, file_part_num, file_name):
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
            clinic_notes: are these the clinic notes?
            file_part_num: file part number to be processed 
            file_name: file name of the gzip file to be processed. must have file-part-num string
    """

    # generate file name of gzip file
    # if clinic_notes:
    #     file_name = f"2Blast_part4_{file_part_num}_clinic_notes.parquet.gzip"
    # else:
    #     file_name = f"2Blast_part4_{file_part_num}_results_with_status_dates.parquet.gzip"

    file_name = file_name.replace('file-part-num', str(file_part_num))

    # print file name
    logger.info(file_name)

    # read parquet.gzip file
    df = pd.read_parquet(os.path.join(data_dir, file_name), engine='pyarrow', use_nullable_dtypes = True)
    df.replace({'None': None}, inplace=True)

    # drop rows of patient research id if it is not of the format we want
    pattern = r'^[A-Z]{2}\d{5}[A-Z]{2}\.R$'

    # filter the dataframe
    df = df.loc[df['PATIENT_RESEARCH_ID'].notna()].copy()
    df = df[df['PATIENT_RESEARCH_ID'].str.match(pattern)].copy()

    # rename certain columns
    if clinic_notes:
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

    # if clinic, make adjustments to the dataframe
    if clinic_notes:
        # df = df.loc[df['note_text'].apply(lambda x: len(x.strip())) > 1].copy()
        df = df.loc[df['note_text'].apply(lambda x: True if pd.isna(x) else len(x.strip()) > 1)].copy()
        # add EPR date
        df['epr_date'] = df['note_date'].fillna(df['effective_date_time'])

    # add mrn column
    mrns = pd.read_csv(mrn_file)
    if 'PATIENT_RESEARCH_ID' in mrns.columns:
        mrns = mrns.rename(columns={'PATIENT_RESEARCH_ID': 'RESEARCH_ID'})
    # change type of RSEARCH_ID to string and MRN to int64
    mrns['RESEARCH_ID'] = mrns['RESEARCH_ID'].astype('string')
    mrns['MRN'] = mrns['MRN'].astype('int64')
    mrn_map = dict(zip(mrns['RESEARCH_ID'], mrns['MRN']))
    df['mrn'] = df['PATIENT_RESEARCH_ID'].map(mrn_map)

    epic_notes_raw_df = None
    if clinic_notes:
        epic_notes_raw_df = df.loc[~df['ClinicNotes.ClinicNote.summary'].isna()].copy()
        df = df.loc[df['ClinicNotes.ClinicNote.summary'].isna()].copy()

    # extract only procedures of interest (if condition if clinic)
    PROCEDURE_NAMES_OF_INTEREST_EPR = [
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
        'History',
        'Discharge Summary Report',
        'Medical Records Report-PMH',
        'Medical Records Letter',
        'Geriatric Clinic Note',
        'Annual Examination'
    ]

    # root_dir = '/cluster/projects/gliugroup/2BLAST'
    # proc_names_category = pd.read_csv(f'{root_dir}/data/info/proc_names.csv')
    # RAD_PROCEDURE_NAMES_OF_INTEREST = proc_names_category.query('category == "Radiology"')['value'].tolist()

    # PROCEDURE_NAMES_OF_INTEREST_EPR.extend(RAD_PROCEDURE_NAMES_OF_INTEREST)

    # need to edit this for clinic notes
    mask = df[proc_name_col].isin(PROCEDURE_NAMES_OF_INTEREST_EPR)
    df = df[mask].copy()    

    # create metadata column
    if clinic_notes:
        df['meta_data'], df['text_data'] = zip(*df['note_text'].apply(lambda x: split_metadata_col_clinic(x)))
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
        'clinical_note', # this is for clinic notes
        'fax number',
        'relation to patient',
        'fax number',
        'instructions',
        'medical records letter'
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

    # make adjustments if clinic notes case
    if clinic_notes:
        # drop rows which have duplicate values for text_data if meta data is in other_meta
        df_all_other_meta = df.loc[~df['meta_data'].str.lower().isin(other_metadata)].copy()
        df_physician_meta = df.loc[df['meta_data'].str.lower().isin(other_metadata)].copy()
        df_physician_meta.drop_duplicates(subset=['PATIENT_RESEARCH_ID', 'clinical_note_id', 'meta_data', 'text_data'], inplace=True)
        df = pd.concat([df_all_other_meta, df_physician_meta], axis=0)

        # merge text values if the meta_data is the same
        # this can happen since the note is sometimes split such as
        # 14001/Medical Records Report: Date of Visit: 17 Jan 2019
        # 14001/Medical Records Report: Dear Dr. X:
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

    # # save debug
    # df_meta_of_interest.to_csv(f"{save_dir}/debug_prepivot_{file_part_num}.csv", index=False)

    # pivot data frame to desired format
    df_meta_of_interest['meta_data'] = df_meta_of_interest['meta_data'].astype(str)
    df_meta_of_interest['text_data'] = df_meta_of_interest['text_data'].astype(str)
    pivot_data_df = df_meta_of_interest.pivot_table('text_data', cols_to_group_by, 'meta_data', aggfunc=lambda x: ' '.join(x))
    pivot_data_df.reset_index(drop=False, inplace=True)
    pivot_data_df = pivot_data_df.rename_axis(None, axis=1)

    # # save debug
    # pivot_data_df.to_csv(f"{save_dir}/debug_postpivot_{file_part_num}.csv", index=False)

    # count the number of patients
    n_patient_obs = df_meta_of_interest[['PATIENT_RESEARCH_ID', visit_id_col]].copy().drop_duplicates().shape[0]
    if pivot_data_df.shape[0] != n_patient_obs:
        logger.info("Warning: duplicate rows after pivoting\n")
    # assert np.allclose(pivot_data_df.shape[0], n_patient_obs), "Number of observations does not match number of patients"

    # fix any duplicate rows in pivot_data_df heuristically
    group_1_cols = ['mrn', 'PATIENT_RESEARCH_ID', visit_id_col]
    group_2_cols = [col for col in cols_to_group_by if col not in group_1_cols]
    group_3_cols = [col for col in pivot_data_df if col not in group_1_cols + group_2_cols]
    agg_funcs = {col: 'first' for col in group_1_cols}  # Take the first value (all are the same)
    agg_funcs.update({col: lambda x: x[x != 'dummy'].iloc[0] if (x != 'dummy').any() else 'dummy' for col in group_2_cols})
    agg_funcs.update({col: lambda x: x.bfill().iloc[0] for col in group_3_cols})  # get any value

    pivot_data_df = pivot_data_df.groupby(['PATIENT_RESEARCH_ID', visit_id_col], as_index=False).agg(agg_funcs)

    # if clinic, fix Medical Records Report meta data
    if clinic_notes:
        mask = (pivot_data_df['medical_records_report'] == 'Medical Records Report') & pivot_data_df['clinical_note'].notna()
        pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']
        mask = pivot_data_df['medical_records_report'].isna() & pivot_data_df['clinical_note'].notna()
        pivot_data_df.loc[mask, 'medical_records_report'] = pivot_data_df.loc[mask, 'clinical_note']
        # need to see an example of clinical note metadata

    # merge all notes into a clinical_notes column
    # cols_to_agg_master = ['medical_records_report', 'textualreport', 'note', 'additional_details', 
    #                       'document_more_advice', 'reason_for_communication', 'information_given', 
    #                       'reason_for_call', 'comment', 'person_calling', 'e_mail_address', 
    #                       'communication_with', 'spoke_with', 'phone_number', 'fax_number', 
    #                       'relation_to_patient']
    cols_to_agg_master = list(map_notes_meta.values())
    cols_to_agg_local = [x for x in cols_to_agg_master if x in pivot_data_df.columns]
    if clinic_notes: cols_to_agg_local.remove('clinical_note')
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].astype(str)
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].replace(to_replace='nan', value="")
    pivot_data_df[cols_to_agg_local] = pivot_data_df[cols_to_agg_local].replace(to_replace='None', value="")
    # if medical_records_report column has value Medical Records Report, empty cell
    pivot_data_df.loc[pivot_data_df['medical_records_report'] == 'Medical Records Report', 'medical_records_report'] = ''
    # if note column has value Note, empty cell
    pivot_data_df.loc[pivot_data_df['note'] == 'Note', 'note'] = ''
    pivot_data_df['clinical_notes'] = pivot_data_df[cols_to_agg_local].agg('\n\n'.join, axis=1)
    pivot_data_df.drop(columns=cols_to_agg_local, inplace=True)
    if 'clinical_note' in pivot_data_df.columns: 
        pivot_data_df.drop(columns='clinical_note', inplace=True)

    # apply correction to the date 
    if clinic_notes:
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
    if clinic_notes:
        df_last_updated = get_last_updated_clinic_ci_notes(json_dir, file_part_num, file_name, PROCEDURE_NAMES_OF_INTEREST_EPR)
    else:
        df_last_updated = get_last_updated(json_dir, file_part_num, file_name, PROCEDURE_NAMES_OF_INTEREST_EPR)
    pivot_data_df = pivot_data_df.merge(df_last_updated, how='left', on=['PATIENT_RESEARCH_ID', visit_id_col])

    # pivot_data_df = pivot_data_df.loc[pivot_data_df['clinical_notes'] != '\n'*len(cols_to_agg_master)].copy()
    pivot_data_df['new_line_only'] = pivot_data_df['clinical_notes'].apply(lambda x: all(char == '\n' for char in x))
    pivot_data_df = pivot_data_df.loc[pivot_data_df['new_line_only'] == False]
    pivot_data_df.drop('new_line_only', axis=1, inplace=True)

    if epic_notes_raw_df is not None and not epic_notes_raw_df.empty:
        # process epic notes if present
        PROCEDURE_NAMES_OF_INTEREST_EPIC = [
            'PROGRESS', 'OP NOTE', 'Teleconsult', 'CONSULT', 'H&P',
            'Disch Summ', 'ED Prov Note', 'Post-Proc', 'MEDICAL STUD', 'CARE PLAN',
            'Code Doc', 'PATIENT CARE', 'PROCEDURE', 'TELEPHONE EN', 'AN Preproc',
            'Anes Procs', 'AN Postproc', 'Dictated Let', 'PATIENT INST', 'PRE-PROCEDUR',
            'Radiation Th', 'MCC Note', 'A&P Note', 'Sedation Doc', 'Txp', 'CCRT Note',
            'AN CAC', 'Comm Rev', 'Dial Round', 'Research Not', 'Dent Proc', 'Rad Comp',
            'ACP', 'Pre-Proc', 'Event', 'ED Note', 'Nursing', 'BRIEF OP NOT',
            'Pre-Sedation', 'Rx MedRec', 'ED Procedure', 'Interval H&P', 'H&P(View-Onl',
            'Care Plan', 'Care and Ser', 'Dial Month', 'Rad Plan', 'SADR', 'Report',
            'Group Note', 'SubjObj', 'Attestation', 'ICC Note', 'OR NURSING',
            'Hospital Cou', 'ED Triage No', 'PFAx', 'BMT Planning'
        ]
        epic_notes_raw_df = epic_notes_raw_df.loc[epic_notes_raw_df['code_text'].isin(PROCEDURE_NAMES_OF_INTEREST_EPIC)]

        pattern = r"Author Type:\s*([^\nF]+(?:F(?!iled:)[^\nF]*)*)"
        epic_notes_raw_df['Extracted_Author_Type'] = epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].str.extract(pattern)
        epic_notes_raw_df['Extracted_Author_Type'] = epic_notes_raw_df['Extracted_Author_Type'].str.replace(r"^\s+|\s+$", "", regex=True)

        # filter out according to extracted author type
        author_types = ['Resident', 'Fellow', 'Physician', 'Medical Student', '', 'Research Fellow']
        epic_notes_raw_df = epic_notes_raw_df.loc[epic_notes_raw_df['Extracted_Author_Type'].isin(author_types)].copy()

        # extract header from EPIC note
        epic_notes_raw_df['Header_Info'] = epic_notes_raw_df["ClinicNotes.ClinicNote.summary"].apply(lambda x: extract_header(x))

        # extract date from EPIC notes
        epic_notes_raw_df["Header_Date"] = epic_notes_raw_df["Header_Info"].str.extract(r"by .*? at (\d{1,2}/\d{1,2}/\d{4})")
        epic_notes_raw_df["Filed_Date"] = epic_notes_raw_df["Header_Info"].str.extract(r"Filed: (\d{1,2}/\d{1,2}/\d{4})")
        epic_notes_raw_df["Header_Date"] = pd.to_datetime(epic_notes_raw_df["Header_Date"], format="%d/%m/%Y")
        epic_notes_raw_df["Filed_Date"] = pd.to_datetime(epic_notes_raw_df["Filed_Date"], format="%d/%m/%Y")
        # fix Header_Date if year is less than 2020
        mask = epic_notes_raw_df["Header_Date"].dt.year < 2020
        epic_notes_raw_df.loc[mask, "Header_Date"] = epic_notes_raw_df.loc[mask, "Filed_Date"]

        # extract physician name from header
        epic_notes_raw_df["Header_Author"] = epic_notes_raw_df["Header_Info"].str.extract(r"by (.+?) at")
        epic_notes_raw_df["Header_Author"] = epic_notes_raw_df["Header_Author"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
        epic_notes_raw_df["Header_Author"] = epic_notes_raw_df["Header_Author"].str.replace(r",?\s*MD\b.*$", "", regex=True)
        epic_notes_raw_df["Cosigner"] = epic_notes_raw_df["Header_Info"].str.extract(r"Cosigner:\s*([\w\s,.\-()']+)\s+at")
        epic_notes_raw_df["Cosigner"] = epic_notes_raw_df["Cosigner"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
        epic_notes_raw_df["Cosigner"] = epic_notes_raw_df["Cosigner"].str.replace(r",?\s*MD\b.*$", "", regex=True)

        epic_notes_raw_df['EPIC_FLAG'] = 1

        # map physician names
        epic_notes_raw_df['Header_Author'] = epic_notes_raw_df['Header_Author'].replace(aliasDictionary)
        epic_notes_raw_df['Cosigner'] = epic_notes_raw_df['Cosigner'].replace(aliasDictionary)

        # clean the "bmk" at the beginning and end lines
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'] = epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(remove_bmk_lines)

        # drop duplicates based on extra whie spaces
        epic_notes_raw_df['remove_white_space_notes'] = epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(lambda x: re.sub(r'\s+', '', x))
        epic_notes_raw_df = epic_notes_raw_df.drop_duplicates(subset=['remove_white_space_notes'])

        # only save columns that we need, add EPIC flag column
        # we will not save the epr_date (system date) in this case
        epic_notes_raw_df.rename(columns={"ClinicNotes.ClinicNote.summary": "clinical_notes",
            "Header_Date": "visit_date", "Header_Author": "processed_physician_name"}, inplace=True)
        
        cols_to_keep = ['mrn', 'PATIENT_RESEARCH_ID', 'clinical_note_id', 'code_text','encounter_reference',
                            'clinical_notes', 'visit_date', 'processed_physician_name', 'Cosigner', 'EPIC_FLAG']

        pivot_data_df = pd.concat([pivot_data_df, epic_notes_raw_df[cols_to_keep]], ignore_index=True, sort=False)

    # strip trailing line break/space from the column clinical_notes
    pivot_data_df['clinical_notes'] = pivot_data_df['clinical_notes'].apply(lambda x: x.rstrip())

    # save extracted data
    if clinic_notes:
        pivot_data_df.to_parquet(f"{save_dir}/processed_clinic_notes_{file_part_num}.parquet.gzip", compression='gzip', index=False)
    else:
        pivot_data_df.to_parquet(f"{save_dir}/processed_observation_notes_{file_part_num}.parquet.gzip", compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help="data directory", type=str)  # data directory
    parser.add_argument("json_dir", help = "json directory", type = str) # json directory
    parser.add_argument("save_dir", help = "save directory", type = str) # save directory
    parser.add_argument("mrn_file", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("clinic_notes", help = "MRN clinic notes", type = int) # clinic notes after 2017
    parser.add_argument("file_part_num", help = "file part number", type = int) # file part number
    parser.add_argument("file_name", help = "file name", type = str) # file name
    args = parser.parse_args()

    process_notes(args.data_dir, args.json_dir, args.save_dir, 
                  args.mrn_file, args.clinic_notes, args.file_part_num,
                  args.file_name)