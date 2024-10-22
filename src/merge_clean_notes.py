import pandas as pd
import argparse
import os
from util import (extract_date_from_note, 
                  extract_job_num, 
                  parallelize,
                  strip_title)
from functools import partial
from process_notes import process_notes
import logging

logger = logging.getLogger(__name__)

def merge_clean_notes(data_dir_observations, data_dir_clinical, 
                      json_dir_observations, json_dir_clinical,
                      mrn_file, save_dir, file_part_max_observations,
                      file_part_max_clinical):
    """
    Process each observation notes and clinic notes and merge
    them into 1 dataframe. Clean processed clinical notes by 
    replacing the date with date in note if available and dropping 
    duplicates according to extracted job number and date last updated.

    data_dir_observations: directory path of the parquet.gzip files for observations
    data_dir_clinical: directory path of the parquet.gzip files for clinical
    json_dir_observations: directory path of the json files for observations
    json_dir_clinical: directory path of the json files for clinical
    mrn_file: mrn file
    save_dir: directory path where merged parquet file will be saved
    file_part_max_observations: maximum number of files for the observations notes
    file_part_max_clinical: maximum number of files for the clinical notes
    """

    # apply parallel processing to process each dataframe for clinic (missing) 

    # worker = partial(process_notes, data_dir=data_dir_clinical, 
    #                  json_dir=json_dir_clinical, 
    #                  save_dir=save_dir,
    #                  mrn_file=mrn_file, 
    #                  missing_notes=1)
    worker = partial(process_notes, data_dir_clinical, 
                     json_dir_clinical, 
                     save_dir,
                     mrn_file, 
                     1)
    generator = list(range(file_part_max_clinical + 1))
    out = parallelize(generator, worker, processes=os.cpu_count())

    # apply parallel processing to process each dataframe for observation (non-missing)

    # worker = partial(process_notes, data_dir=data_dir_observations, 
    #                  json_dir=json_dir_observations, 
    #                  save_dir=save_dir,
    #                  mrn_file=mrn_file, 
    #                  missing_notes=0)
    worker = partial(process_notes, data_dir_observations, 
                     json_dir_observations, 
                     save_dir,
                     mrn_file, 
                     0)
    generator = list(range(file_part_max_observations + 1))
    out = parallelize(generator, worker, processes=os.cpu_count())

    # merge dataframes
    merged_notes = dict()
    for note_type in ['observations', 'clinical']:
        if note_type == 'observations':
            fname = 'processed_clinical_notes'
            file_part_max = file_part_max_observations
        else:
            fname = 'processed_missing_clinical_notes'
            file_part_max = file_part_max_clinical
        
        merged_notes_list = []
        for ctr in range(file_part_max + 1):
            # load dataframe
            df_temp = pd.read_parquet(os.path.join(save_dir, f'{fname}_{ctr}.parquet.gzip'), 
                                      engine='pyarrow', use_nullable_dtypes = True)
            merged_notes_list.append(df_temp)
        merged_notes[note_type] = pd.concat(merged_notes_list)
        merged_notes[note_type]['visit_date'] = pd.to_datetime(merged_notes[note_type]['visit_date'], utc=True)
        merged_notes[note_type]['last_updated'] = pd.to_datetime(merged_notes[note_type]['last_updated'].apply(
            lambda x: x.replace('T', ' ').replace('Z','')[:19]), utc=True, format='%Y-%m-%d %H:%M:%S')

    # merge the observations and clinical dataframe

    cols_to_keep_observations = ['mrn', 'Observations.ProcName', 'clinical_notes', 
                                 'visit_date', 'processed_physician_name', 
                                 'last_updated', 'dictated_by']
    merged_notes['observations'] = merged_notes['observations'][cols_to_keep_observations].copy()

    cols_to_keep_clinical = ['mrn', 'note_text', 'clinical_notes', 
                             'visit_date', 'processed_physician_name', 
                             'last_updated', 'dictated_by']
    merged_notes['clinical'] = merged_notes['clinical'][cols_to_keep_clinical].copy()
    merged_notes['clinical'].rename(columns={'note_text':"Observations.ProcName"}, inplace=True)
    notes_df = pd.concat([merged_notes['observations'], merged_notes['clinical']], ignore_index=True)

    # add physician name
    mask_not_null = notes_df['dictated_by'].notnull()
    notes_df.loc[mask_not_null, 'dictated_by'] = notes_df.loc[mask_not_null, 'dictated_by'].apply(lambda x: strip_title(x))
  
    # extract date from note
    notes_df['date_in_note'] = notes_df['clinical_notes'].apply(lambda x: extract_date_from_note(x))
    notes_df['date_in_note'] = pd.to_datetime(notes_df['date_in_note'], utc=True, format='mixed', errors='coerce' ) 
    notes_df['processed_date'] = notes_df['date_in_note'].copy()
    mask_date_out_of_range = (notes_df['date_in_note'].dt.year < 2004) | (notes_df['date_in_note'].dt.year > 2022)
    notes_df.loc[mask_date_out_of_range, 'processed_date' ] = notes_df.loc[mask_date_out_of_range, 'visit_date']
    mask_null_dates = notes_df['date_in_note'].isnull()
    notes_df.loc[mask_null_dates, 'processed_date'] = notes_df.loc[mask_null_dates, 'visit_date']
    notes_df.rename(columns={"visit_date": "epr_date"}, inplace=True)

    # check that there is no-nan entry in the processed date
    assert sum(notes_df['processed_date'].isnull()) == 0 , "There is a nan date in the processed dates."

    # delete duplicates
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
    
    logger.info(f'Number of duplicate records dropped: {to_clean_notes_df.shape[0] - filtered_records.shape[0]}')

    # filtered notes
    merged_notes_drop_duplicates = pd.concat([notes_df.loc[~notes_df['job_id'].isin(job_id_w_duplicates)], filtered_records]).reset_index()

    cols_to_keep = ['mrn', 'Observations.ProcName', 'processed_physician_name', 'processed_date', 'clinical_notes', 'epr_date', 'dictated_by']
    merged_notes_drop_duplicates[cols_to_keep].to_parquet(f'{save_dir}/merged_processed_cleaned_clinical_notes.parquet.gzip', compression='gzip', index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir_observations", help = "data directory for observations notes", type = str) # data directory for observations notes
    parser.add_argument("data_dir_clinical", help = "data directory for clinical notes", type = str) # data directory for clinical notes
    parser.add_argument("json_dir_observations", help = "json directory for observations notes", type = str) # json directory for observations notes
    parser.add_argument("json_dir_clinical", help = "json directory for clinical notes", type = str) # json directory for clinical notes
    parser.add_argument("mrn_file", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("save_dir", help = "save directory of merged notes", type = str) # save directory for merged notes
    parser.add_argument("file_part_max_observations", help = "maximum file part number for observations", type = int) # maximum file part number for observations
    parser.add_argument("file_part_max_clinical", help = "maximum file part number for clinical", type = int) # maximum file part number for clinical
    args = parser.parse_args()

    merge_clean_notes(args.data_dir_observations, args.data_dir_clinical, 
                      args.json_dir_observations, args.json_dir_clinical,
                      args.mrn_file, args.save_dir, args.file_part_max_observations, 
                      args.file_part_max_clinical)
