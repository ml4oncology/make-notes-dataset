import pandas as pd
import argparse
import os
from util import (extract_date_from_note, 
                  extract_job_num,
                  clean_clinical_note,
                  strip_title)
import logging

logger = logging.getLogger(__name__)
import sys
sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/info")
from phys_names import aliasDictionary

def merge_clean_notes(parquet_gzip_dir, file_part_max_observations,
                      file_part_max_clinical):
    """
    Process each observation notes and clinic notes and merge
    them into 1 dataframe. Clean processed clinical notes by 
    replacing the date with date in note if available and dropping 
    duplicates according to extracted job number and date last updated.

    parquet_gzip_dir: directory path where the parquet gzip files are stored
    file_part_max_observations: maximum number of files for the observations notes
    file_part_max_clinical: maximum number of files for the clinical notes
    """

    # merge dataframes
    merged_notes = dict()
    for note_type in ['observations', 'clinical']:
        if note_type == 'observations':
            fname = 'processed_observation_notes'
            file_part_max = file_part_max_observations
            dir_name = 'obs_notes_parts'
        else:
            fname = 'processed_clinic_notes'
            file_part_max = file_part_max_clinical
            dir_name = 'clinic_notes_parts'
        
        merged_notes_list = []
        for ctr in range(file_part_max + 1):
            # load dataframe
            df_temp = pd.read_parquet(os.path.join(parquet_gzip_dir, dir_name, f'{fname}_{ctr}.parquet.gzip'), 
                                      engine='pyarrow', use_nullable_dtypes = True)
            merged_notes_list.append(df_temp)
        merged_notes[note_type] = pd.concat(merged_notes_list)
        merged_notes[note_type]['visit_date'] = pd.to_datetime(merged_notes[note_type]['visit_date'], utc=True)
        merged_notes[note_type]['last_updated'] = pd.to_datetime(
            merged_notes[note_type]['last_updated'].apply(
                lambda x: x.replace('T', ' ').replace('Z', '')[:19] if isinstance(x, str) else pd.NaT
            ),
            utc=True,
            format='%Y-%m-%d %H:%M:%S'
        )

    # merge the observations and clinical dataframe

    cols_to_keep = ['mrn', 'Observations.ProcName', 'clinical_notes', 
                    'visit_date', 'processed_physician_name', 
                    'last_updated', 'dictated_by']
    merged_notes['clinical'].rename(columns={'code_text':"Observations.ProcName"}, inplace=True)
    merged_notes['observations'] = merged_notes['observations'][cols_to_keep].copy()
    clinical_cols = cols_to_keep.copy()
    for optional in ['Cosigner', 'EPIC_FLAG']:
        if optional in merged_notes['clinical'].columns:
            clinical_cols.append(optional)
    merged_notes['clinical'] = merged_notes['clinical'][clinical_cols].copy()
    notes_df = pd.concat([merged_notes['observations'], merged_notes['clinical']], ignore_index=True)

    # # add physician name
    # mask_not_null = notes_df['dictated_by'].notnull()
    # notes_df.loc[mask_not_null, 'dictated_by'] = notes_df.loc[mask_not_null, 'dictated_by'].apply(lambda x: strip_title(x))
    epic_df = None
    if 'EPIC_FLAG' in notes_df.columns:
        notes_df['EPIC_FLAG'] = notes_df['EPIC_FLAG'].apply(lambda x: 1 if x == 1 else 0)
        epic_df = notes_df[notes_df['EPIC_FLAG'] == 1]
        notes_df = notes_df[notes_df['EPIC_FLAG'] != 1]

    # extract date from note
    notes_df['date_in_note'] = notes_df['clinical_notes'].apply(lambda x: extract_date_from_note(x))
    notes_df['date_in_note'] = pd.to_datetime(notes_df['date_in_note'], utc=True, format='mixed', errors='coerce' ) 
    notes_df['processed_date'] = notes_df['date_in_note'].copy()
    # for EPR notes, if the year is beyond 2022, replace the date with visit date
    mask_beyond_2022 = (notes_df['date_in_note'].dt.year > 2022)
    notes_df.loc[mask_beyond_2022, 'processed_date'] = notes_df.loc[mask_beyond_2022, 'visit_date']
    # mask_date_out_of_range = (notes_df['date_in_note'].dt.year < 2004) | (notes_df['date_in_note'].dt.year > 2022)
    mask_date_out_of_range = (notes_df['date_in_note'].dt.year < 2004)
    notes_df.loc[mask_date_out_of_range, 'processed_date' ] = notes_df.loc[mask_date_out_of_range, 'visit_date']
    mask_null_dates = notes_df['date_in_note'].isnull()
    notes_df.loc[mask_null_dates, 'processed_date'] = notes_df.loc[mask_null_dates, 'visit_date']
    notes_df.rename(columns={"visit_date": "epr_date"}, inplace=True)

    notes_df['last_updated'] = pd.to_datetime(notes_df['last_updated'], utc=True)
    
    # check that there is no-nan entry in the processed date
    assert sum(notes_df['processed_date'].isnull()) == 0 , "There is a nan date in the processed dates."

    # delete duplicates among EPR notes
    notes_df['job_id'] = notes_df['clinical_notes'].apply(lambda x: extract_job_num(x))
    # find notes with duplicity more than 1
    df_with_job_id = notes_df.loc[notes_df['job_id'].notnull()].copy()
    df_job_id_count = df_with_job_id.groupby(['job_id']).size().reset_index(name='job_id_count')
    job_id_w_duplicates = list(df_job_id_count.loc[df_job_id_count['job_id_count'] > 1]['job_id'].unique())
    
    # sort by last updated
    to_clean_notes_df = notes_df.loc[notes_df['job_id'].isin(job_id_w_duplicates)].copy()
    to_clean_notes_df.sort_values(by='last_updated', ascending=False, inplace=True)
    # group by MRN, procedure name, and job id. keep only the first record
    filtered_records = to_clean_notes_df.groupby(['mrn', 'Observations.ProcName', 'job_id']).first().reset_index()

    # check that for the same job id and procedure name, there are no duplicates anymore
    df_with_job_id = filtered_records.loc[filtered_records['job_id'].notnull()].copy()
    df_job_id_count = df_with_job_id.groupby(['mrn', 'Observations.ProcName', 'job_id']).size().reset_index(name='job_id_count')
    assert df_job_id_count['job_id_count'].max() == 1, "There is a duplicate record with the same procedure name."
    
    logger.info(f'Number of duplicate EPR records dropped based on job id: {to_clean_notes_df.shape[0] - filtered_records.shape[0]}')

    # filtered notes
    merged_notes_drop_duplicates_temp = pd.concat([notes_df.loc[~notes_df['job_id'].isin(job_id_w_duplicates)], filtered_records]).reset_index()

    # remove leading white space from notes
    merged_notes_drop_duplicates_temp['clinical_notes'] = merged_notes_drop_duplicates_temp['clinical_notes'].apply(lambda x: x.lstrip())

    # drop duplicates based on 'clinical_notes' and 'processed_date'
    merged_notes_drop_duplicates = merged_notes_drop_duplicates_temp.drop_duplicates(subset=['clinical_notes', 'processed_date'])

    logger.info(f'Duplicates dropped among EPR notes based on identical note and date: {merged_notes_drop_duplicates_temp.shape[0] - merged_notes_drop_duplicates.shape[0]}')

    if epic_df is not None:
        # delete duplicates among EPIC notes
        before_drop = len(epic_df)
        epic_df_deduped = epic_df.drop_duplicates(subset='clinical_notes')
        after_drop = len(epic_df_deduped)

        logger.info(f'Duplicates dropped among EPIC notes: {before_drop - after_drop}')

        epic_df_deduped.rename(columns={"visit_date": "processed_date"}, inplace=True)
        epic_df_deduped['dictated_by'] = epic_df_deduped['processed_physician_name']
        epic_df_deduped[['clinical_notes', 'removed_text']] = epic_df_deduped['clinical_notes'].apply(lambda x: pd.Series(clean_clinical_note(x)))
        # drop removed_text column
        epic_df_deduped.drop(columns=['removed_text'], inplace=True)

        merged_notes_drop_duplicates = pd.concat([merged_notes_drop_duplicates, epic_df_deduped], ignore_index=True)

    cols_to_keep = ['mrn', 'Observations.ProcName', 'processed_physician_name', 'processed_date', 'clinical_notes', 'epr_date', 'dictated_by', 'Cosigner', 'EPIC_FLAG']
    existing_cols = [col for col in cols_to_keep if col in merged_notes_drop_duplicates.columns]

    merged_notes_drop_duplicates[existing_cols].to_parquet(f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes.parquet.gzip', compression='gzip', index=False)

    # find the list of medical oncologists from the aliasDictionary
    unique_aliases = []
    for _, values in aliasDictionary.items():
        unique_aliases.append(values)
    unique_aliases = list(set(unique_aliases))

    # apply the alias mapping to processed_physician_name
    merged_notes_drop_duplicates['processed_physician_name'] = merged_notes_drop_duplicates['processed_physician_name'].replace(aliasDictionary)
    # if Cosigner is a column, apply the alias mapping to Cosigner as well
    if 'Cosigner' in merged_notes_drop_duplicates.columns:
        merged_notes_drop_duplicates['Cosigner'] = merged_notes_drop_duplicates['Cosigner'].replace(aliasDictionary)

    # restrict merged_notes_drop_duplicates[existing_cols] such that processed_physician_name or Cosigner is in unique_aliases
    # if Cosigner exists, keep rows where either processed_physician_name or Cosigner is in unique_aliases

    anchored_proc_names = ['Clinic Note', 'Letter', 'History & Physical Note', 
                    'Consultation Note', 'Clinic Note (Non-dictated)']
    if 'Cosigner' in merged_notes_drop_duplicates.columns:
        mask = (
            merged_notes_drop_duplicates['processed_physician_name'].isin(unique_aliases) |
            merged_notes_drop_duplicates['Cosigner'].isin(unique_aliases) & (
            (merged_notes_drop_duplicates['EPIC_FLAG'] == 1) |
            (merged_notes_drop_duplicates['Observations.ProcName'].isin(anchored_proc_names))
            )
        )
    else:
        mask = ( merged_notes_drop_duplicates['processed_physician_name'].isin(unique_aliases) & 
                merged_notes_drop_duplicates['Observations.ProcName'].isin(anchored_proc_names)
        )

    medonc_notes_df = merged_notes_drop_duplicates.loc[mask, existing_cols].copy()    
    medonc_notes_df.to_parquet(f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes_medonc_only.parquet.gzip', compression='gzip', index=False)

    # if EPIC_FLAG is in the columns of medonc_notes_df, only keep the records with EPIC_FLAG == 1 and save
    if 'EPIC_FLAG' in medonc_notes_df.columns:
        medonc_notes_df_epic = medonc_notes_df[medonc_notes_df['EPIC_FLAG'] == 1].copy()
        medonc_notes_df_epic.to_parquet(f'{parquet_gzip_dir}/merged_processed_cleaned_clinical_notes_medonc_only_epic.parquet.gzip', compression='gzip', index=False)
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet_gzip_dir", help = "directory of the parquet gzip files", type = str) # directory of the parquet gzip files
    parser.add_argument("file_part_max_observations", help = "maximum file part number for observations", type = int) # maximum file part number for observations
    parser.add_argument("file_part_max_clinical", help = "maximum file part number for clinical", type = int) # maximum file part number for clinical
    args = parser.parse_args()

    merge_clean_notes(args.parquet_gzip_dir, args.file_part_max_observations, 
                      args.file_part_max_clinical)
