import sys
import numpy as np
import pandas as pd
import os
import argparse
import logging
import re

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

from util import (process_date, process_physician,
                  get_last_updated_obs_notes,
                  get_last_updated_clinic_ci_notes,
                  extract_header)

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/info")
from phys_names import aliasDictionary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
    'Annual Examination',
]

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
    'Hospital Cou', 'ED Triage No', 'PFAx', 'BMT Planning',
]

NOTES_METADATA = [
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
    'clinical_note',  # this is for clinic notes
    'fax number',
    'relation to patient',
    'fax number',
    'instructions',
    'medical records letter',
]

OTHER_METADATA = [
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

PATIENT_ID_PATTERN = r'^[A-Z]{2}\d{5}[A-Z]{2}\.R$'

AUTHOR_TYPES_OF_INTEREST = ['Resident', 'Fellow', 'Physician', 'Medical Student', '', 'Research Fellow']


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

def remove_bmk_lines(text):
    """Remove leading/trailing 'bmk' lines and strip non-blank lines."""
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
    """Split a clinic note cell into (meta_data, text_data).

    Expected format: '10060/Report Type: Clinic Note'.
    If the cell is a raw clinic note (contains newlines), returns
    ('clinical_note', note_text). Falls back to ('undefined', note_text).
    """
    if '\n' in note_text:
        return 'clinical_note', note_text

    if '/' in note_text:
        slash_position = note_text.index('/')
        colon_position = note_text.index(':')
        meta_data = note_text[slash_position + 1:colon_position]
        text_data = note_text[colon_position + 2:]

        if meta_data[0] == '/' or (len(meta_data) > 1 and meta_data[1] == '/'):
            slash_position = meta_data.index('/')
            meta_data = meta_data[slash_position + 1:]

        return meta_data, text_data

    return 'undefined', note_text


# ---------------------------------------------------------------------------
# Metadata column builders
# ---------------------------------------------------------------------------

def create_metadata(df):
    """Create metadata columns for the observation-notes dataframe."""
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
    df.loc[df['component_code_display'].notnull(), 'meta_data'] = \
        df['component_code_display'].loc[df['component_code_display'].notnull()]
    df['meta_data'] = df['meta_data'].str.lower()
    # clinical notes is split into 2 columns in the raw data frame
    notes_mask = (df['component_extension_url'] == 'NOTES')
    df.loc[notes_mask, 'text_data'] = df['component_extension_value_string'].loc[notes_mask]

    return df[columns_to_keep].copy()


def build_metadata_maps():
    """Return (map_notes_meta, map_other_meta) dicts mapping raw metadata labels
    to column-safe names (spaces/hyphens/slashes replaced with underscores)."""
    map_notes_meta = {
        elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_')
        for elem in NOTES_METADATA
    }
    map_other_meta = {
        elem: elem.replace(' ', '_').replace('-', '_').replace('/', '_').replace("'", '_')
        for elem in OTHER_METADATA
    }
    return map_notes_meta, map_other_meta


# ---------------------------------------------------------------------------
# Data loading and initial filtering
# ---------------------------------------------------------------------------

def load_raw_data(data_dir, file_name, file_part_num):
    """Load the raw parquet file, replacing string 'None' with actual None."""
    file_name = file_name.replace('file-part-num', str(file_part_num))
    logger.info(file_name)
    df = pd.read_parquet(os.path.join(data_dir, file_name), engine='pyarrow', use_nullable_dtypes=True)
    df.replace({'None': None}, inplace=True)
    return df, file_name


def filter_valid_patient_ids(df):
    """Keep only rows whose PATIENT_RESEARCH_ID matches the expected format."""
    df = df.loc[df['PATIENT_RESEARCH_ID'].notna()].copy()
    df = df[df['PATIENT_RESEARCH_ID'].str.match(PATIENT_ID_PATTERN)].copy()
    return df


def rename_columns(df, clinic_notes_dir):
    """Rename raw columns to standardised names; return (df, proc_name_col, visit_id_col)."""
    if clinic_notes_dir:
        new_column_names = {
            'ClinicNotes.ClinicNote.note.text': 'note_text',
            'ClinicNotes.ClinicNote.date': 'note_date',
            'ClinicNotes.ClinicNote.effectiveDateTime': 'effective_date_time',
            'ClinicNotes.ClinicNote._id': 'clinical_note_id',
            'ClinicNotes.ClinicNote.code.text': 'code_text',
            'ClinicNotes.ClinicNote.encounter.reference': 'encounter_reference',
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
    return df, proc_name_col, visit_id_col


def apply_clinic_note_adjustments(df):
    """Drop empty notes and add epr_date for the clinic-notes case."""
    df = df.loc[df['note_text'].apply(lambda x: True if pd.isna(x) else len(x.strip()) > 1)].copy()
    df['epr_date'] = df['note_date'].fillna(df['effective_date_time'])
    return df


def attach_mrn(df, mrn_file):
    """Map PATIENT_RESEARCH_ID to MRN and add an 'mrn' column."""
    mrns = pd.read_csv(mrn_file)
    if 'PATIENT_RESEARCH_ID' in mrns.columns:
        mrns = mrns.rename(columns={'PATIENT_RESEARCH_ID': 'RESEARCH_ID'})
    mrns['RESEARCH_ID'] = mrns['RESEARCH_ID'].astype('string')
    mrns['MRN'] = mrns['MRN'].astype('int64')
    mrn_map = dict(zip(mrns['RESEARCH_ID'], mrns['MRN']))
    df['mrn'] = df['PATIENT_RESEARCH_ID'].map(mrn_map)
    return df


def split_epic_notes(df):
    """Split a clinic-notes dataframe into EPR rows and EPIC rows."""
    epic_df = df.loc[~df['ClinicNotes.ClinicNote.summary'].isna()].copy()
    epr_df = df.loc[df['ClinicNotes.ClinicNote.summary'].isna()].copy()
    return epr_df, epic_df


# ---------------------------------------------------------------------------
# Metadata filtering and pivoting
# ---------------------------------------------------------------------------

def deduplicate_clinic_metadata(df):
    """For clinic notes, de-duplicate physician-level metadata rows and merge
    text values that share the same metadata category."""
    df_all_other_meta = df.loc[~df['meta_data'].str.lower().isin(OTHER_METADATA)].copy()
    df_physician_meta = df.loc[df['meta_data'].str.lower().isin(OTHER_METADATA)].copy()
    df_physician_meta.drop_duplicates(
        subset=['PATIENT_RESEARCH_ID', 'clinical_note_id', 'meta_data', 'text_data'],
        inplace=True,
    )
    df = pd.concat([df_all_other_meta, df_physician_meta], axis=0)
    # merge text values if the meta_data is the same
    # this can happen since the note is sometimes split such as
    # 14001/Medical Records Report: Date of Visit: 17 Jan 2019
    # 14001/Medical Records Report: Dear Dr. X:
    group_by_cols = [
        'mrn', 'PATIENT_RESEARCH_ID', 'clinical_note_id',
        'code_text', 'epr_date', 'encounter_reference', 'meta_data',
    ]
    df_grouped = (
        df.groupby(group_by_cols)
        .agg(text_data=('text_data', lambda x: '\n'.join(x)))
        .reset_index()
    )
    df_grouped['meta_data'] = df_grouped['meta_data'].str.lower()
    return df_grouped


def filter_and_pivot_metadata(df, map_meta):
    """Retain only metadata rows of interest and pivot to one-row-per-visit."""
    df_meta = df.loc[df['meta_data'].isin(NOTES_METADATA + OTHER_METADATA)].copy()

    if 'Observations.ProcCode' in df_meta.columns:
        df_meta['Observations.ProcCode'] = df_meta['Observations.ProcCode'].astype(int)

    df_meta['meta_data'] = df_meta['meta_data'].map(map_meta)
    cols_to_group_by = [col for col in df_meta.columns if col not in ['meta_data', 'text_data']]

    df_meta[cols_to_group_by] = df_meta[cols_to_group_by].fillna(value="dummy")
    df_meta['meta_data'] = df_meta['meta_data'].astype(str)
    df_meta['text_data'] = df_meta['text_data'].astype(str)

    pivot_df = df_meta.pivot_table(
        'text_data', cols_to_group_by, 'meta_data',
        aggfunc=lambda x: ' '.join(x),
    )
    pivot_df.reset_index(drop=False, inplace=True)
    pivot_df = pivot_df.rename_axis(None, axis=1)

    return pivot_df, df_meta


def deduplicate_pivot(pivot_df, df_meta, visit_id_col):
    """Heuristically resolve any duplicate rows introduced by pivoting."""
    n_patient_obs = df_meta[['PATIENT_RESEARCH_ID', visit_id_col]].drop_duplicates().shape[0]
    if pivot_df.shape[0] != n_patient_obs:
        logger.info("Warning: duplicate rows after pivoting\n")

    group_1_cols = ['mrn', 'PATIENT_RESEARCH_ID', visit_id_col]
    group_2_cols = [col for col in df_meta.columns if col not in group_1_cols + ['meta_data', 'text_data']]
    group_3_cols = [col for col in pivot_df.columns if col not in group_1_cols + group_2_cols]

    agg_funcs = {col: 'first' for col in group_1_cols}
    agg_funcs.update({
        col: (lambda x: x[x != 'dummy'].iloc[0] if (x != 'dummy').any() else 'dummy')
        for col in group_2_cols
    })
    agg_funcs.update({col: lambda x: x.bfill().iloc[0] for col in group_3_cols})

    pivot_df = pivot_df.groupby(['PATIENT_RESEARCH_ID', visit_id_col], as_index=False).agg(agg_funcs)
    return pivot_df


# ---------------------------------------------------------------------------
# Post-pivot cleanup and aggregation
# ---------------------------------------------------------------------------

def fix_medical_records_report(pivot_df):
    """For clinic notes, replace placeholder 'Medical Records Report' values
    with the actual clinical note text where available."""
    mask = (
        (pivot_df['medical_records_report'] == 'Medical Records Report')
        & pivot_df['clinical_note'].notna()
    )
    pivot_df.loc[mask, 'medical_records_report'] = pivot_df.loc[mask, 'clinical_note']

    mask = pivot_df['medical_records_report'].isna() & pivot_df['clinical_note'].notna()
    pivot_df.loc[mask, 'medical_records_report'] = pivot_df.loc[mask, 'clinical_note']
    return pivot_df


def aggregate_notes_columns(pivot_df, map_notes_meta, clinic_notes_dir):
    """Merge all individual note columns into a single 'clinical_notes' column."""
    cols_to_agg_master = list(map_notes_meta.values())
    cols_to_agg_local = [x for x in cols_to_agg_master if x in pivot_df.columns]

    if clinic_notes_dir:
        cols_to_agg_local.remove('clinical_note')

    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].astype(str)
    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].replace(to_replace='nan', value="")
    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].replace(to_replace='None', value="")

    # if medical_records_report column has value Medical Records Report, empty cell
    pivot_df.loc[pivot_df['medical_records_report'] == 'Medical Records Report', 'medical_records_report'] = ''
    # if note column has value Note, empty cell
    pivot_df.loc[pivot_df['note'] == 'Note', 'note'] = ''

    pivot_df['clinical_notes'] = pivot_df[cols_to_agg_local].agg('\n\n'.join, axis=1)
    pivot_df.drop(columns=cols_to_agg_local, inplace=True)

    if 'clinical_note' in pivot_df.columns:
        pivot_df.drop(columns='clinical_note', inplace=True)

    return pivot_df


def apply_date_corrections(pivot_df, clinic_notes_dir):
    """Parse and normalise the visit date column."""
    if clinic_notes_dir:
        pivot_df['date_dictated'] = pd.to_datetime(pivot_df['date_dictated'], utc=True, format='mixed')
        pivot_df['epr_date'] = pd.to_datetime(pivot_df['epr_date'], utc=True)
        pivot_df['visit_date'] = pivot_df['date_dictated'].dt.date

        visit_date_null_mask = pivot_df['visit_date'].isna() & pivot_df['epr_date'].notna()
        pivot_df.loc[visit_date_null_mask, 'visit_date'] = \
            pivot_df.loc[visit_date_null_mask, 'epr_date'].dt.date
    else:
        pivot_df = process_date(pivot_df)
    return pivot_df


def drop_empty_note_rows(pivot_df):
    """Remove rows where 'clinical_notes' contains nothing but newlines."""
    pivot_df['new_line_only'] = pivot_df['clinical_notes'].apply(
        lambda x: all(char == '\n' for char in x)
    )
    pivot_df = pivot_df.loc[pivot_df['new_line_only'] == False]
    pivot_df.drop('new_line_only', axis=1, inplace=True)
    return pivot_df


# ---------------------------------------------------------------------------
# EPIC notes processing
# ---------------------------------------------------------------------------

def process_epic_notes(epic_notes_raw_df):
    """Filter, enrich, and clean the EPIC notes dataframe."""
    epic_notes_raw_df = epic_notes_raw_df.loc[
        epic_notes_raw_df['code_text'].isin(PROCEDURE_NAMES_OF_INTEREST_EPIC)
    ]

    # Extract and clean author type
    author_pattern = r"Author Type:\s*([^\nF]+(?:F(?!iled:)[^\nF]*)*)"
    epic_notes_raw_df['Extracted_Author_Type'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].str.extract(author_pattern)
    )
    epic_notes_raw_df['Extracted_Author_Type'] = (
        epic_notes_raw_df['Extracted_Author_Type'].str.replace(r"^\s+|\s+$", "", regex=True)
    )
    epic_notes_raw_df = epic_notes_raw_df.loc[
        epic_notes_raw_df['Extracted_Author_Type'].isin(AUTHOR_TYPES_OF_INTEREST)
    ].copy()

    # Extract header and derived fields
    epic_notes_raw_df['Header_Info'] = (
        epic_notes_raw_df["ClinicNotes.ClinicNote.summary"].apply(extract_header)
    )
    epic_notes_raw_df["Header_Date"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"by .*? at (\d{1,2}/\d{1,2}/\d{4})")
    )
    epic_notes_raw_df["Filed_Date"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"Filed: (\d{1,2}/\d{1,2}/\d{4})")
    )
    epic_notes_raw_df["Header_Date"] = pd.to_datetime(epic_notes_raw_df["Header_Date"], format="%d/%m/%Y")
    epic_notes_raw_df["Filed_Date"] = pd.to_datetime(epic_notes_raw_df["Filed_Date"], format="%d/%m/%Y")

    # Fix Header_Date when year is before 2020
    mask = epic_notes_raw_df["Header_Date"].dt.year < 2020
    epic_notes_raw_df.loc[mask, "Header_Date"] = epic_notes_raw_df.loc[mask, "Filed_Date"]

    # Extract and clean physician names
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"by (.+?) at")
    )
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Author"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
    )
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Author"].str.replace(r",?\s*MD\b.*$", "", regex=True)
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"Cosigner:\s*([\w\s,.\-()']+)\s+at")
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Cosigner"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Cosigner"].str.replace(r",?\s*MD\b.*$", "", regex=True)
    )

    epic_notes_raw_df['EPIC_FLAG'] = 1

    # Normalise physician name aliases
    epic_notes_raw_df['Header_Author'] = epic_notes_raw_df['Header_Author'].replace(aliasDictionary)
    epic_notes_raw_df['Cosigner'] = epic_notes_raw_df['Cosigner'].replace(aliasDictionary)

    # Clean 'bmk' lines from note text
    epic_notes_raw_df['ClinicNotes.ClinicNote.summary'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(remove_bmk_lines)
    )

    # Drop near-duplicate notes (differing only in whitespace)
    epic_notes_raw_df['remove_white_space_notes'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(lambda x: re.sub(r'\s+', '', x))
    )
    epic_notes_raw_df = epic_notes_raw_df.drop_duplicates(subset=['remove_white_space_notes'])

    # Rename and select final columns
    epic_notes_raw_df.rename(columns={
        "ClinicNotes.ClinicNote.summary": "clinical_notes",
        "Header_Date": "visit_date",
        "Header_Author": "processed_physician_name",
    }, inplace=True)

    cols_to_keep = [
        'mrn', 'PATIENT_RESEARCH_ID', 'clinical_note_id', 'code_text',
        'encounter_reference', 'clinical_notes', 'visit_date',
        'processed_physician_name', 'Cosigner', 'EPIC_FLAG',
    ]
    return epic_notes_raw_df[cols_to_keep]


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def process_notes(data_dir, json_dir, save_dir, mrn_file, clinic_notes_dir, file_part_num, file_name):
    """Process each dataset pulled by the CDI team.

    Restricts to a few procedures only. The resulting dataframe has one row per
    patient visit, including visit metadata (MRN, patient code, visit code,
    attending physician, date, etc.) and the clinical note for that visit.

    Args:
        data_dir: directory path where the raw zip files are saved
        json_dir: directory path where the raw json files are saved
        save_dir: directory path where the processed dataframe will be saved
        mrn_file: file path for the patient-code-to-MRN map
        clinic_notes_dir: True/1 if these come from clinic notes directory, False/0 otherwise
        file_part_num: file part number to be processed
        file_name: file name of the gzip file; must contain 'file-part-num' token
    """
    # --- Load and pre-filter ---
    df, file_name = load_raw_data(data_dir, file_name, file_part_num)
    df = filter_valid_patient_ids(df)
    df, proc_name_col, visit_id_col = rename_columns(df, clinic_notes_dir)

    df = attach_mrn(df, mrn_file)

    # --- Split EPIC notes out (clinic-notes path only) ---
    epic_notes_raw_df = None
    if clinic_notes_dir:
        df = apply_clinic_note_adjustments(df)
        df, epic_notes_raw_df = split_epic_notes(df)

    # --- Filter to procedures of interest ---
    # must do this only on EPR notes
    df = df[df[proc_name_col].isin(PROCEDURE_NAMES_OF_INTEREST_EPR)].copy()

    # --- Prepare metadata maps and de-duplicate (clinic-notes path) ---
    map_notes_meta, map_other_meta = build_metadata_maps()
    map_meta = {**map_notes_meta, **map_other_meta}

    # --- Build metadata columns ---
    if clinic_notes_dir:
        df['meta_data'], df['text_data'] = zip(*df['note_text'].apply(split_metadata_col_clinic))
        df = df.reset_index()
        df = deduplicate_clinic_metadata(df)
    else:
        df = create_metadata(df)

    # --- Filter metadata and pivot ---
    pivot_data_df, df_meta_of_interest = filter_and_pivot_metadata(df, map_meta)
    pivot_data_df = deduplicate_pivot(pivot_data_df, df_meta_of_interest, visit_id_col)

    # --- Post-pivot cleanup ---
    if clinic_notes_dir:
        pivot_data_df = fix_medical_records_report(pivot_data_df)

    pivot_data_df = aggregate_notes_columns(pivot_data_df, map_notes_meta, clinic_notes_dir)
    pivot_data_df = apply_date_corrections(pivot_data_df, clinic_notes_dir)
    pivot_data_df = process_physician(pivot_data_df)

    # --- Merge last-updated timestamps ---
    if clinic_notes_dir:
        df_last_updated = get_last_updated_clinic_ci_notes(
            json_dir, file_part_num, file_name, PROCEDURE_NAMES_OF_INTEREST_EPR
        )
    else:
        df_last_updated = get_last_updated_obs_notes(
            json_dir, file_part_num, file_name, PROCEDURE_NAMES_OF_INTEREST_EPR
        )
    pivot_data_df = pivot_data_df.merge(
        df_last_updated, how='left', on=['PATIENT_RESEARCH_ID', visit_id_col]
    )

    # --- Drop rows that are nothing but newlines ---
    pivot_data_df = drop_empty_note_rows(pivot_data_df)

    # --- Merge EPIC notes if present ---
    if epic_notes_raw_df is not None and not epic_notes_raw_df.empty:
        epic_notes_processed = process_epic_notes(epic_notes_raw_df)
        pivot_data_df = pd.concat([pivot_data_df, epic_notes_processed], ignore_index=True, sort=False)

    # --- Final text cleanup ---
    pivot_data_df['clinical_notes'] = pivot_data_df['clinical_notes'].apply(lambda x: x.rstrip())

    # --- Save output ---
    if clinic_notes_dir:
        out_path = f"{save_dir}/processed_clinic_notes_dir_{file_part_num}.parquet.gzip"
    else:
        out_path = f"{save_dir}/processed_observation_notes_{file_part_num}.parquet.gzip"
    pivot_data_df.to_parquet(out_path, compression='gzip', index=False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help="data directory", type=str)
    parser.add_argument("json_dir", help="json directory", type=str)
    parser.add_argument("save_dir", help="save directory", type=str)
    parser.add_argument("mrn_file", help="MRN file", type=str)
    parser.add_argument("clinic_notes_dir", help="clinic notes dir flag (1 = clinic notes)", type=int)
    parser.add_argument("file_part_num", help="file part number", type=int)
    parser.add_argument("file_name", help="file name", type=str)
    args = parser.parse_args()

    process_notes(
        args.data_dir, args.json_dir, args.save_dir,
        args.mrn_file, args.clinic_notes_dir, args.file_part_num,
        args.file_name,
    )