import numpy as np
import pandas as pd
import os
import argparse
import logging
from .util import (process_date, process_physician, 
                   get_last_updated,
                   get_last_updated_missing_ci_notes)

logger = logging.getLogger(__name__)

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
        file_name = f"2Blast_part4_{file_part_num}_clinic_notes.csv"
    else:
        file_name = f"2Blast_part4_{file_part_num}_results_with_status_dates-output.zip"

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
            'ClinicNotes.ClinicNote._id': 'clinical_note_id'
        }
    else:
        new_column_names = {
            'Observations.Observation._id': 'observation_id',
            'Observations.OccurrenceDateTimeFromOrder': 'occurrence_date_time_from_order',
            'Observations.Observation.effectiveDateTime': 'effective_date_time',
            'Observations.Observation.component.code.text': 'component_code_text',
            'Observations.Observation.component.code.coding.0.display': 'component_code_display',
            'Observations.Observation.component.extension.2.url': 'component_extension_url',
            'Observations.Observation.component.valueString': 'component_value_string',
            'Observations.Observation.component.extension.2.valueString': 'component_extension_value_string',
        }
          # pivot data frame to desired format
        # clinical notes is split into 2 columns in raw dataframe
    # df['component_descriptor'] = df['Observations.Observation.component.code.text'].copy()
    # df.loc[df['Observations.Observation.component.code.coding.0.display'].notnull(), 'component_descriptor'] = \
    #     df['Observations.Observation.component.code.coding.0.display'].loc[df['Observations.Observation.component.code.coding.0.display'].notnull()]
    # df['component_descriptor'] = df['component_descriptor'].str.lower()
    # notes_mask = (df['Observations.Observation.component.extension.2.url'] == 'NOTES')
    # df.loc[notes_mask, 'Observations.Observation.component.valueString'] = df['Observations.Observation.component.extension.2.valueString'].loc[notes_mask]

        #   df_meta_of_interest['Observations.ProcCode'] = df_meta_of_interest['Observations.ProcCode'].astype(int)
    # df_meta_of_interest['Observations.Observation.component.valueString'] = df_meta_of_interest['Observations.Observation.component.valueString'].astype(str)
    # df_meta_of_interest['component_descriptor'] = df_meta_of_interest['component_descriptor'].astype(str)
    # pivot_data_df = df_meta_of_interest.pivot_table('Observations.Observation.component.valueString', cols_to_group_by, 'component_descriptor', aggfunc=lambda x: ' '.join(x))
    # pivot_data_df.reset_index(drop=False, inplace=True)
    # pivot_data_df = pivot_data_df.rename_axis(None, axis=1)



    # if missing:
    # make these adjustments
    # df = df.loc[df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: len(x.strip())) > 1].copy()
    # # add EPR date
    # df['epr_date'] = df['ClinicNotes.ClinicNote.date'].fillna(df['ClinicNotes.ClinicNote.effectiveDateTime'])

    # add mrn column

    # extract only procedures of interest (if condition if missing)

    # work on meta-data (if missing, special if condition)

    # filter cols to keep if not missing

    # filter out the component_descriptor (metadata) we care about

    # if missing, do this:
        # drop rows which have duplicate values for text_data if meta_data is in other_meta

        # df_all_other_meta = df.loc[~df['meta_data'].isin(other_meta)].copy()

        # df_physician_meta = df.loc[df['meta_data'].isin(other_meta)].copy()

        # df_physician_meta.drop_duplicates(subset=['PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'meta_data', 'text_data'], inplace=True)

        # df = pd.concat([df_all_other_meta, df_physician_meta], axis=0)



        # # merge text values if the meta_data is the same

        # group_by_cols = ['mrn', 'PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'ClinicNotes.ClinicNote.code.text', 'epr_date', 'ClinicNotes.ClinicNote.encounter.reference', 'meta_data']

        # df_grouped = df.groupby(group_by_cols).agg(text_data=('text_data', lambda x: '\n'.join(x))).reset_index()

        # df_grouped['meta_data'] = df_grouped['meta_data'].str.lower()



     # remove special characters in metadata name to facilitate transition to column names

     # retain only metadata of interest

     # map metadata names to facilitate transition to column names upon pivoting

     # fill the null values with "dummy" to pivot the dataframe

      # pivot data frame to desired format

      # if missing, # fix Medical Records Report metadata

      # # merge all notes into a clinical_notes column

      # apply correction to the date (if condition for missing, not missing)

      # apply correction to the physician name (missing, not missing)

      # if missing: pivot_data_df = pivot_data_df.loc[pivot_data_df['clinical_notes'] != '\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n'].copy()

      # save extracted dataif __name__ == "__main__":
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