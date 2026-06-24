import sys
import os
import argparse
import logging

import pandas as pd

from util import (extract_date_from_note,
                  extract_job_num,
                  clean_clinical_note)

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/info")
from phys_names import aliasDictionary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Procedure names used when filtering med-onc notes without a Cosigner column
ANCHORED_PROC_NAMES = [
    'Clinic Note',
    'Letter',
    'History & Physical Note',
    'Consultation Note',
    'Clinic Note (Non-dictated)',
]

# Columns that must be present; optional ones are appended when available
BASE_COLS_TO_KEEP_CLINICAL_NOTES = [
    'mrn',
    'Observations.ProcName',
    'clinical_notes',
    'visit_date',
    'processed_physician_name',
    'last_updated',
    'dictated_by',
]

OPTIONAL_COLS = ['Cosigner', 'EPIC_FLAG']

FINAL_COLS_ORDER = [
    'mrn', 'Observations.ProcName', 'processed_physician_name',
    'processed_date', 'clinical_notes', 'epr_date', 'dictated_by',
    'Cosigner', 'EPIC_FLAG',
]

BASE_COLS_TO_KEEP_IMAGING_REPORTS = [
    'mrn',
    'Observations.ProcName',
    'imaging_report',
    'visit_date',
    'verified_by',
    'read_by'
]


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_note_parts(parquet_gzip_dir, dir_name, fname, file_part_max):
    """Load and concatenate all part files for one note type.

    Parses visit_date and last_updated into UTC-aware datetimes.
    """
    parts = []
    for ctr in range(file_part_max + 1):
        path = os.path.join(parquet_gzip_dir, dir_name, f'{fname}_{ctr}.parquet.gzip')
        parts.append(pd.read_parquet(path, engine='pyarrow', use_nullable_dtypes=True))

    df = pd.concat(parts)
    df['visit_date'] = pd.to_datetime(df['visit_date'], utc=True)
    if 'last_updated' in df.columns:
        df['last_updated'] = pd.to_datetime(
            df['last_updated'].apply(
                lambda x: x.replace('T', ' ').replace('Z', '')[:19] if isinstance(x, str) else pd.NaT
            ),
            utc=True,
            format='%Y-%m-%d %H:%M:%S',
        )
    return df


def load_and_merge_note_types_clinical_notes(parquet_gzip_dir, file_part_max_observations, file_part_max_clinical):
    """Load observation and clinic note parts and combine into a single dataframe."""
    obs_df = load_note_parts(
        parquet_gzip_dir, 'obs_notes_parts',
        'processed_observation_notes', file_part_max_observations,
    )
    clinic_df = load_note_parts(
        parquet_gzip_dir, 'clinic_notes_parts',
        'processed_clinic_notes', file_part_max_clinical,
    )

    # Align column names before merging
    clinic_df.rename(columns={'code_text': 'Observations.ProcName'}, inplace=True)

    obs_df = obs_df[BASE_COLS_TO_KEEP_CLINICAL_NOTES].copy()

    clinical_cols = BASE_COLS_TO_KEEP_CLINICAL_NOTES.copy()
    for col in OPTIONAL_COLS:
        if col in clinic_df.columns:
            clinical_cols.append(col)
    clinic_df = clinic_df[clinical_cols].copy()

    return pd.concat([obs_df, clinic_df], ignore_index=True)


def load_and_merge_note_types_imaging_reports(parquet_gzip_dir, file_part_max_observations):
    """Load imaging report parts and combine into a single dataframe."""
    img_df = load_note_parts(
        parquet_gzip_dir, 'obs_notes_parts',
        'processed_observation_notesprocessed_pe_dvt_imaging_report', file_part_max_observations,
    )

    return img_df[BASE_COLS_TO_KEEP_IMAGING_REPORTS].copy()

# ---------------------------------------------------------------------------
# EPIC / EPR splitting
# ---------------------------------------------------------------------------

def split_epic_epr(notes_df):
    """Separate EPIC rows from EPR rows.

    Returns (epr_df, epic_df). epic_df is None when EPIC_FLAG is absent.
    """
    if 'EPIC_FLAG' not in notes_df.columns:
        return notes_df, None

    notes_df['EPIC_FLAG'] = notes_df['EPIC_FLAG'].apply(lambda x: 1 if x == 1 else 0)
    epic_df = notes_df[notes_df['EPIC_FLAG'] == 1].copy()
    epr_df = notes_df[notes_df['EPIC_FLAG'] != 1].copy()
    return epr_df, epic_df


# ---------------------------------------------------------------------------
# Date processing
# ---------------------------------------------------------------------------

def resolve_processed_date(notes_df):
    """Derive 'processed_date' from the date embedded in the note text,
    falling back to the visit date when out of range or missing.

    Also renames visit_date → epr_date and asserts no nulls remain.
    """
    notes_df['date_in_note'] = notes_df['clinical_notes'].apply(extract_date_from_note)
    notes_df['date_in_note'] = pd.to_datetime(
        notes_df['date_in_note'], utc=True, format='mixed', errors='coerce'
    )
    notes_df['processed_date'] = notes_df['date_in_note'].copy()

    # Replace out-of-range dates with the visit date
    # for EPR notes, if the year is beyond 2022, replace the date with visit date
    mask_beyond_2022 = notes_df['date_in_note'].dt.year > 2022
    notes_df.loc[mask_beyond_2022, 'processed_date'] = notes_df.loc[mask_beyond_2022, 'visit_date']

    mask_before_2004 = notes_df['date_in_note'].dt.year < 2004
    notes_df.loc[mask_before_2004, 'processed_date'] = notes_df.loc[mask_before_2004, 'visit_date']

    mask_null = notes_df['date_in_note'].isnull()
    notes_df.loc[mask_null, 'processed_date'] = notes_df.loc[mask_null, 'visit_date']

    notes_df.rename(columns={'visit_date': 'epr_date'}, inplace=True)
    notes_df['last_updated'] = pd.to_datetime(notes_df['last_updated'], utc=True)

    assert notes_df['processed_date'].isnull().sum() == 0, \
        "There is a nan date in the processed dates."

    return notes_df


# ---------------------------------------------------------------------------
# EPR deduplication
# ---------------------------------------------------------------------------

def find_duplicate_job_ids(notes_df):
    """Return the list of job IDs that appear more than once."""
    df_with_job_id = notes_df.loc[notes_df['job_id'].notnull()]
    job_id_counts = df_with_job_id.groupby('job_id').size().reset_index(name='job_id_count')
    return job_id_counts.loc[job_id_counts['job_id_count'] > 1, 'job_id'].unique().tolist()


def deduplicate_by_job_id(notes_df):
    """For EPR notes with duplicate job IDs, keep only the most recently updated record."""
    notes_df['job_id'] = notes_df['clinical_notes'].apply(extract_job_num)
    job_id_w_duplicates = find_duplicate_job_ids(notes_df)

    duplicated_df = notes_df.loc[notes_df['job_id'].isin(job_id_w_duplicates)].copy()
    duplicated_df.sort_values(by='last_updated', ascending=False, inplace=True)
    filtered_records = (
        duplicated_df
        .groupby(['mrn', 'Observations.ProcName', 'job_id'])
        .first()
        .reset_index()
    )

    # Sanity check: no remaining duplicates per (mrn, proc, job_id)
    df_check = filtered_records.loc[filtered_records['job_id'].notnull()]
    counts = df_check.groupby(['mrn', 'Observations.ProcName', 'job_id']).size()
    assert counts.max() == 1, "There is a duplicate record with the same procedure name."

    n_dropped = duplicated_df.shape[0] - filtered_records.shape[0]
    logger.info(f'Number of duplicate EPR records dropped based on job id: {n_dropped}')

    non_duplicated_df = notes_df.loc[~notes_df['job_id'].isin(job_id_w_duplicates)]
    return pd.concat([non_duplicated_df, filtered_records]).reset_index()


def deduplicate_epr_notes(notes_df):
    """Full EPR deduplication: by job ID first, then by identical note + date."""
    notes_df = deduplicate_by_job_id(notes_df)

    # Strip leading whitespace before the exact-match dedup
    notes_df['clinical_notes'] = notes_df['clinical_notes'].apply(str.lstrip)

    before = notes_df.shape[0]
    notes_df = notes_df.drop_duplicates(subset=['clinical_notes', 'processed_date'])
    logger.info(
        f'Duplicates dropped among EPR notes based on identical note and date: {before - notes_df.shape[0]}'
    )
    return notes_df


# ---------------------------------------------------------------------------
# EPIC note processing
# ---------------------------------------------------------------------------

def deduplicate_and_clean_epic_notes(epic_df):
    """Deduplicate EPIC notes and apply clinical-note cleaning."""
    before = len(epic_df)
    epic_df = epic_df.drop_duplicates(subset='clinical_notes').copy()
    logger.info(f'Duplicates dropped among EPIC notes: {before - len(epic_df)}')

    epic_df.rename(columns={'visit_date': 'processed_date'}, inplace=True)
    epic_df['dictated_by'] = epic_df['processed_physician_name']
    epic_df[['clinical_notes', 'removed_text']] = (
        epic_df['clinical_notes'].apply(lambda x: pd.Series(clean_clinical_note(x)))
    )
    epic_df.drop(columns=['removed_text'], inplace=True)
    return epic_df


# ---------------------------------------------------------------------------
# Physician alias filtering
# ---------------------------------------------------------------------------

def get_unique_aliases():
    """Return the deduplicated list of canonical physician names from aliasDictionary."""
    return list(set(aliasDictionary.values()))


def apply_alias_mapping(df):
    """Replace physician name variants with their canonical aliases."""
    df['processed_physician_name'] = df['processed_physician_name'].replace(aliasDictionary)
    if 'Cosigner' in df.columns:
        df['Cosigner'] = df['Cosigner'].replace(aliasDictionary)
    return df


def filter_medonc_notes(df, unique_aliases):
    """Keep only notes authored or co-signed by a known medical oncologist."""
    # restrict merged_notes_drop_duplicates[existing_cols] such that processed_physician_name 
    # or Cosigner is in unique_aliases
    # if Cosigner exists, keep rows where either processed_physician_name or Cosigner is in 
    # unique_aliases
    if 'Cosigner' in df.columns:
        mask = (
            df['processed_physician_name'].isin(unique_aliases) |
            (
                df['Cosigner'].isin(unique_aliases) &
                (
                    (df['EPIC_FLAG'] == 1) |
                    df['Observations.ProcName'].isin(ANCHORED_PROC_NAMES)
                )
            )
        )
    else:
        mask = (
            df['processed_physician_name'].isin(unique_aliases) &
            df['Observations.ProcName'].isin(ANCHORED_PROC_NAMES)
        )
    return df.loc[mask].copy()


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def select_output_cols(df):
    """Return the dataframe restricted to the desired output column order."""
    existing = [col for col in FINAL_COLS_ORDER if col in df.columns]
    return df[existing]


def save_parquet(df, path):
    df.to_parquet(path, compression='gzip', index=False)
    logger.info(f'Saved: {path}')


def save_epic_subsets(medonc_df, parquet_gzip_dir):
    """Save the EPIC-only and EPIC-records-only subsets of med-onc notes."""
    medonc_epic = medonc_df[medonc_df['EPIC_FLAG'] == 1].copy()
    save_parquet(
        medonc_epic,
        f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes_medonc_only_epic.parquet.gzip',
    )

    medonc_epr = medonc_df[medonc_df['EPIC_FLAG'] == 0]
    mrns_epr = set(medonc_epr['mrn'].unique())
    mrns_epic = set(medonc_epic['mrn'].unique())
    mrns_only_epic = mrns_epic - mrns_epr

    medonc_epic_only = medonc_epic[medonc_epic['mrn'].isin(mrns_only_epic)].copy()
    save_parquet(
        medonc_epic_only,
        f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes_medonc_only_epic_records_only.parquet.gzip',
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def merge_clean_notes(parquet_gzip_dir, file_part_max_observations, file_part_max_clinical):
    """Process observation and clinic notes, merge them, clean, and save outputs.

    Cleans processed clinical notes by replacing the date with the date found
    in the note body (when available), and deduplicates by job number and
    last-updated timestamp.

    Args:
        parquet_gzip_dir: directory path where the parquet gzip files are stored
        file_part_max_observations: maximum part number for observation note files
        file_part_max_clinical: maximum part number for clinic note files
    """
    # --- Load and combine all clinical note parts ---
    notes_df = load_and_merge_note_types_clinical_notes(
        parquet_gzip_dir, file_part_max_observations, file_part_max_clinical
    )

    # --- Load and combine all pe/dvt imaging reports ---
    img_df = load_and_merge_note_types_imaging_reports(
        parquet_gzip_dir, file_part_max_observations
    )
    save_parquet(
        img_df,
        f'{parquet_gzip_dir}/merged_pe_dvt_imaging_report.parquet.gzip',
    )

    # --- Separate EPIC notes from EPR notes ---
    notes_df, epic_df = split_epic_epr(notes_df)

    # --- Resolve visit dates for EPR notes ---
    notes_df = resolve_processed_date(notes_df)

    # --- Deduplicate EPR notes ---
    notes_df = deduplicate_epr_notes(notes_df)

    # --- Process and merge EPIC notes if present ---
    if epic_df is not None:
        epic_df = deduplicate_and_clean_epic_notes(epic_df)
        notes_df = pd.concat([notes_df, epic_df], ignore_index=True)

    # --- Save full merged output ---
    all_notes_output = select_output_cols(notes_df)
    save_parquet(
        all_notes_output,
        f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes.parquet.gzip',
    )

    # --- Apply physician alias mapping and filter to med-onc notes ---
    unique_aliases = get_unique_aliases()
    notes_df = apply_alias_mapping(notes_df)
    medonc_df = filter_medonc_notes(notes_df, unique_aliases)
    medonc_output = select_output_cols(medonc_df)

    save_parquet(
        medonc_output,
        f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes_medonc_only.parquet.gzip',
    )

    # --- Save EPIC-specific subsets if the flag column is present ---
    if 'EPIC_FLAG' in medonc_output.columns:
        save_epic_subsets(medonc_output, parquet_gzip_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet_gzip_dir", help="directory of the parquet gzip files", type=str)
    parser.add_argument("file_part_max_observations", help="maximum file part number for observations", type=int)
    parser.add_argument("file_part_max_clinical", help="maximum file part number for clinical", type=int)
    args = parser.parse_args()

    merge_clean_notes(
        args.parquet_gzip_dir,
        args.file_part_max_observations,
        args.file_part_max_clinical,
    )