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