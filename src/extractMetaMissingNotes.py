import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math

def extractMetaMissingNotes(dataDir, saveDir, filePartNum, MRNfile):
    """
    Extract meta data from raw csv files for EDA and to understand structure of 
    notes dataset. This code is to handle the case for the missing notes.

    dataDir: directory path of raw csv files
    saveDir: directory path for saving
    filePartNum: file part number of clinical notes data set
    MRNfile: path to the MRN mapping
    """

    df = pd.read_csv(f'{dataDir}/2Blast_part4_{filePartNum}_clinic_notes.csv')
    df = df.loc[ df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: len(x.strip())) > 1 ]
    # add EPR date
    df['EPRDate'] = df['ClinicNotes.ClinicNote.date']
    df.loc[df['EPRDate'].isna(), 'EPRDate'] = df.loc[df['EPRDate'].isna(), 'ClinicNotes.ClinicNote.effectiveDateTime']

    # add MRN column
    dfMRN = pd.read_csv( MRNfile, dtype={'RESEARCH_ID':'string', 'MRN':'string'} )
    mrnMap = dict( zip(dfMRN['RESEARCH_ID'],dfMRN['MRN']) )
    df['MRN'] = df['PATIENT_RESEARCH_ID'].map( mrnMap )

    def split_metadata_col(note_text):
        print(note_text)
        if '\n' in note_text:
            meta_data = 'clinical_note'
            text_data = note_text
        elif '/' in note_text:
            # find '/'
            slash_position = note_text.index('/')
            # find :
            colon_position = note_text.index(':')
            meta_data = note_text[slash_position+1:colon_position]
            text_data = note_text[colon_position+2:]

            if meta_data[0] == '/' or (len(meta_data) > 1 and meta_data[1] == '/') :
                slash_position = meta_data.index('/')
                meta_data = meta_data[slash_position+1:]
        else:
            meta_data = 'undefined'
            text_data = note_text

        return meta_data, text_data

    df['meta_data'], df['text_data'] = zip(*df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: split_metadata_col(x)))

    # # find the unique note type
    # unique_note_type = df['ClinicNotes.ClinicNote.code.text'].unique().tolist()
    # with open(f"{saveDir}/unique_note_type_{filePartNum}.json", 'w') as f:
    #     json.dump(unique_note_type, f)

    procNames = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',\
                        'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',\
                            'Clinic Note (Non-dictated)', 'Discharge Summary',\
                                'Unscheduled Discharge Summary', 'Operative Note',\
                                     'Progress Notes', 'Letters', 'Consultation Report']

    df = df.loc[ df['ClinicNotes.ClinicNote.code.text'].isin( procNames ) ].copy()

    # find the unique metadata
    meta_data_unique = df['meta_data'].unique().tolist()
    with open(f"{saveDir}/metaData_text_{filePartNum}.json", 'w') as f:
        json.dump(meta_data_unique, f)
    
    grpby_cols = ['MRN', 'PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'ClinicNotes.ClinicNote.code.text', 'EPRDate', 'ClinicNotes.ClinicNote.encounter.reference', 'meta_data'] 
    df_grpd = df.groupby(grpby_cols).agg(text_data=('text_data', lambda x: '\n'.join(x))).reset_index()

    # find the length
    df_grpd['text_data'] = df_grpd['text_data'].astype(str)
    df_grpd['len_of_text_data'] = df_grpd['text_data'].apply(lambda x: len(x))
    df_grpd.sort_values(by='text_data', ascending=False, inplace=True)

    cols_to_keep = ['MRN', 'PATIENT_RESEARCH_ID', 'EPRDate', 'text_data']
    df_grpd_by_meta_data = df_grpd.groupby(['meta_data'])[cols_to_keep].first().reset_index()
    df_grpd_by_meta_data.to_csv(f'{saveDir}/meta_data_longest_str_{filePartNum}.csv')

    # # look at records which have meta data 'clinical_note'
    # clinic_id_clinical_note = df_grpd.loc[df_grpd['meta_data'] == 'clinical_note', 'ClinicNotes.ClinicNote._id'].unique().tolist()
    # df_grpd_clinical_note = df_grpd.loc[df_grpd['ClinicNotes.ClinicNote._id'].isin(clinic_id_clinical_note)].copy()
    # df_grpd_clinical_note.to_csv(f'{saveDir}/clinical_note_metadata_df_{filePartNum}.csv')

    # get unique list of doctors in attending/staff
    physician_name = df_grpd.loc[df_grpd['meta_data'].isin(['Attending/Staff','Dictated by','Documented by']), 'text_data'].unique().tolist()
    with open(f"{saveDir}/unique_physician_names_{filePartNum}.json", 'w') as f:
        json.dump(physician_name, f)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartNum", help = "file part number", type = int) # file part number
    parser.add_argument("MRNfile", help = "MRN file", type = str) # file where MRN is saved
    args = parser.parse_args()

    extractMetaMissingNotes( args.dataDir, args.saveDir, args.filePartNum, args.MRNfile )
