import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math
import re
import sys
sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/clinical_notes/HealthReportRecords/constants")
# load constants from file
from constants import ambigousPhysicians, aliasDictionary

def processDate( df ):
    """
    Process date of visit column according to the following hierarchy:
    date_dictated > Observations.Observation.effectiveDateTime > Observations.OccurrenceDateTimeFromOrder

    df: a dataframe with columns date_dictated, Observations.Observation.effectiveDateTime, Observations.OccurrenceDateTimeFromOrder
    """
    
    # replace dummy dates with None and convert columns to datetime 
    df['Observations.OccurrenceDateTimeFromOrder'].replace('dummy', None, inplace=True)
    df['Observations.Observation.effectiveDateTime'].replace('dummy', None, inplace=True)
    df['Observations.OccurrenceDateTimeFromOrder'] = pd.to_datetime( df['Observations.OccurrenceDateTimeFromOrder'], utc=True )
    df['Observations.Observation.effectiveDateTime'] = pd.to_datetime( df['Observations.Observation.effectiveDateTime'], utc=True )

    # convert date_dictated from string to datetime column by extracting date only and excluding day of week
    maskDateDictated = df['date_dictated'].notnull()
    df.loc[maskDateDictated, 'date_dictated'] = pd.to_datetime( df.loc[maskDateDictated, 'date_dictated'].map( lambda x: x.split(',')[1][1:] ) , format='%d %b %Y')
    df['date_dictated'] = pd.to_datetime( df['date_dictated'], utc=True )

    # create a visit date column according to hierarchy of "accuracy"
    df['visitDate'] = df['date_dictated'].dt.date
    visitDateNullMask = df['visitDate'].isnull()
    df.loc[ visitDateNullMask, 'visitDate' ] = df.loc[ visitDateNullMask, 'Observations.Observation.effectiveDateTime' ].dt.date
    visitDateNullMask = df['visitDate'].isnull()
    df.loc[ visitDateNullMask, 'visitDate' ] = df.loc[ visitDateNullMask, 'Observations.OccurrenceDateTimeFromOrder' ].dt.date

    return df

def stripTitle(x):
    """
    Strip title and single letters from name.

    x: name of physician/staff
    """
    # strip extra white spaces
    x = re.sub(' +', ' ', x)

    # remove known prefixes (not exhaustive)
    if 'Dr. ' in x:
        x = x.replace("Dr. ","")
    elif 'Sr. MS ' in  x:
        x = x.replace("Sr. MS ","")
    elif 'MS ' in x:
        x = x.replace("MS ", "")
    
    # search for ',' and remove everything after
    if ',' in x:
        x = x[:x.find(',')]

    # remove period
    x = x.replace(".","")

    # remove single letters
    # this may affect those with first names abbreviated
    # purpose is only to find the null doctors

    return ' '.join( [w for w in x.split() if len(w)>1] )

def processPhysician( df ):
    """
    Process attending physician name column according to the following hierarchy:
    attending_staff > dictated_by > documented_by > dictated_by_for >  dictated_by_and_or_verified_by_resident_s_attending

    df: a dataframe with columns attending_staff, dictated_by, documented_by
    """

    # check for ambiguous physician names in attending_staff and replace by value in dictated_by
    maskAmbiguous = df['attending_staff'].isin( ambigousPhysicians ) 
    df.loc[ maskAmbiguous, 'attending_staff'] = df.loc[ maskAmbiguous, 'dictated_by' ] 

    # create a physician name column according to hierarchy of "accuracy"
    df['physician_name'] = df['attending_staff'].copy()
    # fill missing ones with dictated_by
    maskNull = df['physician_name'].isnull()
    df.loc[ maskNull, 'physician_name' ] = df.loc[ maskNull, 'dictated_by' ]
    # fill missing ones with documented_by
    maskNull = df['physician_name'].isnull()
    df.loc[ maskNull, 'physician_name' ] = df.loc[ maskNull, 'documented_by' ]
    # fill missing ones with dictated_by_for
    if 'dictated_by_for' in list(df.columns.values):
        maskNull = df['physician_name'].isnull()
        df.loc[ maskNull, 'physician_name' ] = df.loc[ maskNull, 'dictated_by_for' ]
    # fill missing ones with dictated_by_and_or_verified_by_resident_s_attending
    if 'dictated_by_and_or_verified_by_resident_s_attending' in list(df.columns.values):
        maskNull = df['physician_name'].isnull()
        df.loc[ maskNull, 'physician_name' ] = df.loc[ maskNull, 'dictated_by_and_or_verified_by_resident_s_attending' ]

    # strip titles for non-null names
    maskNotNull = df['physician_name'].notnull()
    df['processed_physician_name'] = None
    df.loc[ maskNotNull, 'processed_physician_name' ] = df.loc[ maskNotNull, 'physician_name' ].apply( lambda x: stripTitle(x) ) 

    # map names of medical oncologists to alias
    def map_medOnc(x, medOncMap):
        if x not in medOncMap:
            return x
        else:
            return medOncMap[x]
    
    df.loc[ maskNotNull, 'processed_physician_name' ] = df.loc[ maskNotNull, 'processed_physician_name' ].apply( lambda x: map_medOnc(x, aliasDictionary) )

    return df

def getLastUpdated(jsonDir, filePartNum, procNames):
    """
        Extract the lastUpdated column from the raw json file since it's not present
        in the processed CSV files.

        jsonDir: directory where the raw json files are saved
        filePartNum: file part number to be processed
        procNames: list of procedure names of interest
    """
    # load the json file
    fileName = f"2Blast_part4_{filePartNum}_results_with_status_dates.zip"
    filePath = jsonDir + '/' + fileName

    jsonFileName = f'{jsonDir}/2Blast_part4_{filePartNum}_results_with_status_dates.json'
    if not os.path.isfile( jsonFileName ):
        os.system(f"unzip {filePath} -d {jsonDir}")
    
    with open( jsonFileName ) as json_file:
        data = json.load(json_file)

    # tabulate patient id, obs id, last updated
    
    # procedure names of interest
    procNames = [x.lower() for x in procNames]

    patientList = []
    obsIDList = []
    lastUpdatedList = []

    for idx in range(len(data)):
        nObs = len(data[idx]['Observations'])
        for jdx in range(nObs):
            if str(data[idx]['Observations'][jdx]['ProcName']).lower() in procNames:
                patientList.append( data[idx]['PATIENT_RESEARCH_ID'] )
                obsIDList.append( data[idx]['Observations'][jdx]['Observation']['_id'] )
                lastUpdatedList.append( data[idx]['Observations'][jdx]['Observation']['meta']['lastUpdated'] )

    # delete json file
    os.system(f"rm {jsonDir}/2Blast_part4_{filePartNum}_results_with_status_dates.json")

    dfLastUpdated = pd.DataFrame( {'PATIENT_RESEARCH_ID': patientList, 'Observations.Observation._id': obsIDList, 'lastUpdated': lastUpdatedList} )

    return dfLastUpdated
    

def processClinicalNotes(dataDir, jsonDir, saveDir, MRNfile, filePartNum):
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

    fileName = f"2Blast_part4_{filePartNum}_results_with_status_dates-output.zip"
    filePath = dataDir + '/' + fileName

    # unzip file
    csvFilePath = dataDir + '/' + f"2Blast_part4_{filePartNum}_results_with_status_dates.csv"
    if not os.path.isfile( csvFilePath ):
        os.system(f"unzip {filePath} -d {dataDir}")

    # read data frame
    df = pd.read_csv( csvFilePath )

    # extract only procedures of interest
    procNames = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',\
                        'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',\
                            'Clinic Note (Non-dictated)', 'Discharge Summary',\
                                'Unscheduled Discharge Summary', 'Operative Note',\
                                     'Progress Notes', 'Letters', 'Consultation Report']
    procNames = [x.lower() for x in procNames]
    dfSub = df.loc[ df['Observations.ProcName'].str.lower().isin( procNames ) ].copy()

    # apply fixes

    # create metadata column called 'component_descriptor' by merging 2 columns in raw dataframe
    dfSub['component_descriptor'] = dfSub['Observations.Observation.component.code.text'].copy()
    dfSub.loc[dfSub['Observations.Observation.component.code.coding.0.display'].notnull(), 'component_descriptor'] = \
        dfSub['Observations.Observation.component.code.coding.0.display'].loc[dfSub['Observations.Observation.component.code.coding.0.display'].notnull()]
    dfSub['component_descriptor'] = dfSub['component_descriptor'].str.lower()

    # clinical notes is split into 2 columns in raw dataframe
    notes_mask = ( dfSub['Observations.Observation.component.extension.2.url'] == 'NOTES' )
    dfSub.loc[ notes_mask, 'Observations.Observation.component.valueString' ] = dfSub['Observations.Observation.component.extension.2.valueString'].loc[ notes_mask ]
    
    # add MRN column
    dfMRN = pd.read_csv( MRNfile, dtype={'RESEARCH_ID':'string', 'MRN':'string'} )
    mrnMap = dict( zip(dfMRN['RESEARCH_ID'],dfMRN['MRN']) )
    dfSub['MRN'] = dfSub['PATIENT_RESEARCH_ID'].map( mrnMap )

    # columns to keep
    colsToKeep = ['MRN', 'PATIENT_RESEARCH_ID', 'Observations.ProcCode', 'Observations.ProcName', 'Observations.Observation._id',\
              'Observations.StatusFromOrder', 'Observations.OccurrenceDateTimeFromOrder', 'Observations.Observation.basedOn.0.reference',\
                'Observations.Observation.encounter.reference' , 'Observations.Observation.status', \
                   'Observations.Observation.effectiveDateTime', 'component_descriptor', 'Observations.Observation.component.valueString' ]

    # filter out the component_descriptor (metadata) we care about
    notesMeta = ['medical records report', 'note', 'additional details', 'textualreport', 'document more advice',\
                'reason for communication', 'information given', 'reason for call', 'spoke with', 'phone number', \
                    'comment', 'communication with', 'person calling', 'e-mail address' ]

    otherMeta = ['date dictated', 'dictated by', 'documented by', 'attending/staff', 'report type', 'specialty', 'transcribed by', \
                'family physician', 'department', 'location', 'attending/staff signing off note', 'dictating md verifying note',\
                'dictated by/for',"dictated by and/or verified by/resident's attending"]

    # remove special characters in metadata name to facilitate transition to column names
    mapNotesMeta = {}
    for elem in notesMeta:
        mapNotesMeta[elem] = elem.replace(' ', '_').replace('-','_').replace('/','_')

    mapOtherMeta = {}
    for elem in otherMeta:
        mapOtherMeta[elem] = elem.replace(' ', '_').replace('-','_').replace('/','_').replace("'",'_')

    # retain only metadata of interest
    dfMetaOfInterest = dfSub.loc[ dfSub['component_descriptor'].isin( notesMeta + otherMeta ), colsToKeep ].copy()
    dfMetaOfInterest['Observations.ProcCode'] = dfMetaOfInterest['Observations.ProcCode'].astype(int)

    ################## do some checks
    ################## print file part number
    print(f"Part number is {filePartNum}")

    # ################## is there any _id that's nan?
    # if sum(dfMetaOfInterest['Observations.Observation._id'].isnull()) > 0:
    #     print("first check failed")

    ################## count how many unique patient-observation id pairs there are
    nPatientObs = dfMetaOfInterest[['PATIENT_RESEARCH_ID','Observations.Observation._id']].copy().drop_duplicates().shape[0] 
    # np.save(f"{saveDir}/nPatientObs_{filePartNum}.npy", nPatientObs)

    # map metadata names to facilitate transition to column names upon pivoting
    mapMeta = mapNotesMeta | mapOtherMeta
    dfMetaOfInterest['component_descriptor'] = dfMetaOfInterest['component_descriptor'].map( mapMeta )
    colsToGroupBy = [ col for col in colsToKeep if col not in ['component_descriptor','Observations.Observation.component.valueString' ] ]

    # fill the null values with "dummy" to pivot the dataframe
    dfMetaOfInterest[colsToGroupBy] = dfMetaOfInterest[colsToGroupBy].fillna(value="dummy")

    # pivot data frame to desired format
    dfMetaOfInterest['Observations.Observation.component.valueString'] = dfMetaOfInterest['Observations.Observation.component.valueString'].astype(str)
    dfMetaOfInterest['component_descriptor'] = dfMetaOfInterest['component_descriptor'].astype(str)
    pivotDataDF = dfMetaOfInterest.pivot_table('Observations.Observation.component.valueString', colsToGroupBy, 'component_descriptor', aggfunc=lambda x: ' '.join(x))
    pivotDataDF.reset_index( drop=False, inplace=True )
    pivotDataDF = pivotDataDF.rename_axis(None, axis=1)

    ################## is the shape of the pivoted data frame the same as the number of unique patient-observation pairs?
    if not np.allclose( pivotDataDF.shape[0], nPatientObs ):
        print("check failed")

    # merge all notes into a clinical_notes column
    colsToAggMaster = ['medical_records_report', 'textualreport', 'note', 'additional_details', 'document_more_advice',\
             'reason_for_communication', 'information_given', 'reason_for_call', 'comment', 'person_calling',\
             'e_mail_address', 'communication_with', 'spoke_with', 'phone_number', 'fax_number', 'relation_to_patient']
    colsToAggLocal = [ x for x in colsToAggMaster if x in pivotDataDF.columns ]
    pivotDataDF[colsToAggLocal] = pivotDataDF[colsToAggLocal].astype(str)
    pivotDataDF[colsToAggLocal] = pivotDataDF[colsToAggLocal].replace(to_replace='nan', value="")
    pivotDataDF['clinical_notes'] = pivotDataDF[ colsToAggLocal ].agg('\n\n'.join,axis=1)
    pivotDataDF.drop( columns= colsToAggLocal, inplace=True )

    # apply correction to the date
    pivotDataDF = processDate( pivotDataDF )
    
    # apply correction to the physician name
    pivotDataDF = processPhysician( pivotDataDF )

    # extract and merge lastUpdated column
    dfLastUpdated = getLastUpdated(jsonDir, filePartNum, procNames)
    pivotDataDF = pivotDataDF.merge( dfLastUpdated, how='left', on=['PATIENT_RESEARCH_ID', 'Observations.Observation._id'] )

    # save extracted data
    pivotDataDF.to_csv( f"{saveDir}/processedClinicalNotes_{filePartNum}.csv" )

    # delete csv files
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates.csv")
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates-meta.csv")
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates-msgs.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("jsonDir", help = "json directory", type = str) # json directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("MRNfile", help = "MRN file", type = str) # file where MRN is saved
    parser.add_argument("filePartNum", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    processClinicalNotes( args.dataDir, args.jsonDir, args.saveDir, args.MRNfile, args.filePartNum )
