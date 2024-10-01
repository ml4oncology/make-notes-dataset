import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math
import re
import sys
from util import processPhysician, getLastUpdatedMissingCINotes

def processMissingNotes(dataDir, jsonDir, saveDir, MRNfile, filePartNum):
    """
        Process each part of the data pulled by CDI team. Restrict to a few procedures only.
        Resulting data frame is a single row for each visit of a patient. Row includes information
        about the visit (patient MRN, patient code, visit code, attending physician, date, etc)
        as well as the clinical note for that visit.

        dataDir: directory path where the raw zip files are saved
        jsonDir: directory path where the raw json files are saved
        saveDir: directory path where processed data frame will be saved
        MRNfile: file path for patient code to MRN map
        filePartNum: file part number to be processed
    """

    fileName = f"2Blast_part4_{filePartNum}_clinic_notes.csv"
    filePath = dataDir + '/' + fileName

    # print file name
    print(filePath)

    # read data frame
    df = pd.read_csv(filePath)
    df = df.loc[ df['ClinicNotes.ClinicNote.note.text'].apply(lambda x: len(x.strip())) > 1 ].copy()
    # add EPR date
    df['EPRDate'] = df['ClinicNotes.ClinicNote.date']
    df.loc[df['EPRDate'].isna(), 'EPRDate'] = df.loc[df['EPRDate'].isna(), 'ClinicNotes.ClinicNote.effectiveDateTime']

    # add MRN column
    dfMRN = pd.read_csv( MRNfile, dtype={'RESEARCH_ID':'string', 'MRN':'string'} )
    mrnMap = dict( zip(dfMRN['RESEARCH_ID'],dfMRN['MRN']) )
    df['MRN'] = df['PATIENT_RESEARCH_ID'].map( mrnMap )

    # extract only procedures of interest
    procNames = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',\
                        'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',\
                            'Clinic Note (Non-dictated)', 'Discharge Summary',\
                                'Unscheduled Discharge Summary', 'Operative Note',\
                                     'Progress Notes', 'Letters', 'Consultation Report']

    df = df.loc[ df['ClinicNotes.ClinicNote.code.text'].isin( procNames ) ].copy()

    # create metadata column
    def split_metadata_col(note_text):
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
    df = df.reset_index()

    # filter out the component_descriptor (metadata) we care about
    notesMeta = ['medical records report', 'note', 'additional details', 'textualreport', 'document more advice',\
                'reason for communication', 'information given', 'reason for call', 'spoke with', 'phone number', \
                    'comment', 'communication with', 'person calling', 'e-mail address', 'clinical_note']

    # add clinical_note
    otherMeta = ['date dictated', 'dictated by', 'documented by', 'attending/staff', 'report type', 'specialty', 'transcribed by', \
                'family physician', 'department', 'location', 'attending/staff signing off note', 'dictating md verifying note',\
                'dictated by/for',"dictated by and/or verified by/resident's attending"]
    
    # drop rows which have duplicate values for text_data if meta_data is in otherMeta
    df_allOtherMeta = df.loc[~df['meta_data'].isin(otherMeta)].copy()
    df_physicianMeta = df.loc[df['meta_data'].isin(otherMeta)].copy()
    df_physicianMeta.drop_duplicates(subset=['PATIENT_RESEARCH_ID','ClinicNotes.ClinicNote._id','meta_data','text_data'], inplace=True)
    df = pd.concat([df_allOtherMeta, df_physicianMeta], axis=0)

    # merge text values if the meta data is the same
    grpby_cols = ['MRN', 'PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id', 'ClinicNotes.ClinicNote.code.text', 'EPRDate', 'ClinicNotes.ClinicNote.encounter.reference', 'meta_data'] 
    df_grpd = df.groupby(grpby_cols).agg(text_data=('text_data', lambda x: '\n'.join(x))).reset_index()
    df_grpd['meta_data'] = df_grpd['meta_data'].str.lower()

    # remove special characters in metadata name to facilitate transition to column names
    mapNotesMeta = {}
    for elem in notesMeta:
        mapNotesMeta[elem] = elem.replace(' ', '_').replace('-','_').replace('/','_')

    mapOtherMeta = {}
    for elem in otherMeta:
        mapOtherMeta[elem] = elem.replace(' ', '_').replace('-','_').replace('/','_').replace("'",'_')

    # retain only metadata of interest
    dfMetaOfInterest = df_grpd.loc[ df_grpd['meta_data'].isin( notesMeta + otherMeta ) ].copy()
    
    # map metadata names to facilitate transition to column names upon pivoting
    mapMeta = mapNotesMeta | mapOtherMeta
    dfMetaOfInterest['meta_data'] = dfMetaOfInterest['meta_data'].map( mapMeta )
    colsToGroupBy = [ col for col in dfMetaOfInterest.columns if col not in ['meta_data', 'text_data'] ]

    nPatientObs = dfMetaOfInterest[['PATIENT_RESEARCH_ID','ClinicNotes.ClinicNote._id']].copy().drop_duplicates().shape[0] 

    # fill the null values with "dummy" to pivot the dataframe
    dfMetaOfInterest[colsToGroupBy] = dfMetaOfInterest[colsToGroupBy].fillna(value="dummy")

    # pivot data frame to desired format
    dfMetaOfInterest['meta_data'] = dfMetaOfInterest['meta_data'].astype(str)
    dfMetaOfInterest['text_data'] = dfMetaOfInterest['text_data'].astype(str)
    pivotDataDF = dfMetaOfInterest.pivot_table('text_data', colsToGroupBy, 'meta_data', aggfunc=lambda x: ' '.join(x))
    pivotDataDF.reset_index( drop=False, inplace=True )
    pivotDataDF = pivotDataDF.rename_axis(None, axis=1)

    ################## is the shape of the pivoted data frame the same as the number of unique patient-observation pairs?
    if not np.allclose( pivotDataDF.shape[0], nPatientObs ):
        print("check failed")

    # fix Medical Records Report metadata

    mask = (pivotDataDF['medical_records_report'] == 'Medical Records Report') & pivotDataDF['clinical_note'].notna()
    pivotDataDF.loc[mask, 'medical_records_report'] = pivotDataDF.loc[mask, 'clinical_note']
    mask = pivotDataDF['medical_records_report'].isna() & pivotDataDF['clinical_note'].notna()
    pivotDataDF.loc[mask, 'medical_records_report'] = pivotDataDF.loc[mask, 'clinical_note']

    # merge all notes into a clinical_notes column
    colsToAggMaster = ['medical_records_report', 'textualreport', 'note', 'additional_details', 'document_more_advice',\
             'reason_for_communication', 'information_given', 'reason_for_call', 'comment', 'person_calling',\
             'e_mail_address', 'communication_with', 'spoke_with', 'phone_number', 'fax_number', 'relation_to_patient']
    colsToAggLocal = [ x for x in colsToAggMaster if x in pivotDataDF.columns ]
    pivotDataDF[colsToAggLocal] = pivotDataDF[colsToAggLocal].astype(str)
    pivotDataDF[colsToAggLocal] = pivotDataDF[colsToAggLocal].replace(to_replace='nan', value="")
    pivotDataDF['clinical_notes'] = pivotDataDF[ colsToAggLocal ].agg('\n\n'.join,axis=1)
    pivotDataDF.drop( columns= colsToAggLocal, inplace=True )
    pivotDataDF.drop( columns= 'clinical_note', inplace=True )

    # apply correction to the date
    pivotDataDF['date_dictated'] = pd.to_datetime(pivotDataDF['date_dictated'], utc=True, format='mixed')
    pivotDataDF['EPRDate'] = pd.to_datetime(pivotDataDF['EPRDate'], utc=True)
    pivotDataDF['visitDate'] = pivotDataDF['date_dictated'].dt.date
    visitDateNullMask = pivotDataDF['visitDate'].isnull()
    pivotDataDF.loc[ visitDateNullMask, 'visitDate' ] = pivotDataDF.loc[ visitDateNullMask, 'EPRDate' ].dt.date

    # apply correction to the physician name
    pivotDataDF = processPhysician( pivotDataDF )

    # extract and merge lastUpdated column
    dfLastUpdated = getLastUpdatedMissingCINotes(jsonDir, filePartNum, procNames)
    pivotDataDF = pivotDataDF.merge( dfLastUpdated, how='left', on=['PATIENT_RESEARCH_ID', 'ClinicNotes.ClinicNote._id'] )

    pivotDataDF = pivotDataDF.loc[ pivotDataDF['clinical_notes'] != '\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n' ].copy()

    # save extracted data
    pivotDataDF.to_csv( f"{saveDir}/processedMissingClinicalNotes_{filePartNum}.csv" )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("jsonDir", help = "json directory", type = str) # json directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("MRNfile", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("filePartNum", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    processMissingNotes( args.dataDir, args.jsonDir, args.saveDir, args.MRNfile, args.filePartNum )
