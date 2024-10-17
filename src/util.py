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

def process_date( df ):
    """
    Process date of visit column according to the following hierarchy:
    date_dictated > effective_date_time > occurrence_date_time_from_order

    df: a dataframe with columns date_dictated, effective_date_time, occurrence_date_time_from_order
    """
    
    # replace dummy dates with None and convert columns to datetime 
    df['occurrence_date_time_from_order'].replace('dummy', None, inplace=True)
    df['effective_date_time'].replace('dummy', None, inplace=True)
    df['occurrence_date_time_from_order'] = pd.to_datetime(df['occurrence_date_time_from_order'], utc=True)
    df['effective_date_time'] = pd.to_datetime(df['effective_date_time'], utc=True)

    # convert date_dictated from string to datetime column by extracting date only and excluding day of week
    maskDateDictated = df['date_dictated'].notnull()
    df.loc[maskDateDictated, 'date_dictated'] = pd.to_datetime(df.loc[maskDateDictated, 'date_dictated'].map( lambda x: x.split(',')[1][1:] ) , format='%d %b %Y')
    df['date_dictated'] = pd.to_datetime(df['date_dictated'], utc=True)

    # create a visit date column according to hierarchy of "accuracy"
    df['visit_date'] = df['date_dictated'].dt.date
    visitDateNullMask = df['visit_date'].isnull()
    df.loc[visitDateNullMask, 'visit_date'] = df.loc[visitDateNullMask, 'effective_date_time'].dt.date
    visitDateNullMask = df['visit_date'].isnull()
    df.loc[visitDateNullMask, 'visit_date'] = df.loc[visitDateNullMask, 'occurrence_date_time_from_order'].dt.date

    return df

def extractDateFromNote( x ):
    """
    Extract the date from note. This is heuristic and based on trial and error.
    It is not perfect and all-encompassing.
    Case 1: If it's a radiation therapy note --
    Check if Radiation Therapy Note (originally entered in Mosaiq on * @ *)
    exists in note
    Case 2: 
    Check if note has "date of *:" string, followed by a new
    line character to extract the date

    x: A string representing the clinical note
    """

    # Case 1
    pattern = r'Radiation Therapy Note \(originally entered in Mosaiq on (\w{3} \d{2}, \d{4}) @ \d{2}:\d{2}\)'
    match = re.search(pattern, x)
    if match:
        date_string = match.group(1)
        return date_string
        
    # Case 2
    date_description_list = ['date of visit:', 'date of procedure:', 'date of surgery:', 'date of op:',\
                             'date of operation:', 'date of or:', 'date of service:',\
                             'date of the procedure:', 'date of assessment:']
    xLower = x.lower()
    inText = [ 1 if elem in xLower else 0 for elem in date_description_list ]
    if sum( inText ) == 0:
        return None
    else:
        nonzero_descriptor_id = [idx for idx, val in enumerate(inText) if val != 0]
        return helperDateFromNote(x, date_description_list[ nonzero_descriptor_id[0] ])

    
def helperDateFromNote( x, date_descrip ):
    """
    Helper function for extracting date from note in cases where a substring of the form
    "date of *" is present.

    x: A string representing the clinical note
    date_descrip: A string that indicates the date of the visit. Of the form "date of *"
    """

    # find the first string
    try:
        clear_nl = x.find(next(filter(str.isalpha, x)))
        x = x[clear_nl:]
    
    except StopIteration:
        return None
    
    exists = 0

    # some have a newline after the date description
    idx = x.lower().find(date_descrip)
    date_descrip_nl = date_descrip + '\n'
    if x.lower().find(date_descrip_nl) != -1:
        idx = x.lower().find(date_descrip_nl)
        date_descrip = date_descrip_nl

    x = x[idx + len(date_descrip):]
    if x.find('\n') > 7 and x.find('\n') < 20:
        exists = 1
    elif x.find('<div>') > 7 and x.find('<div>') < 20:
        exists = 1
        
    if exists == 1:

        # find what separates (\n or <div>) from the text that follows
        if '\n' in x:
            idx_nl = x.find('\n')
        else:
            idx_nl = len(x)
        if '<div>' in x:
            idx_div = x.find('<div>')
        else:
            idx_div = len(x)
        idx_stop = min( idx_nl, idx_div )
        date_str = x[:idx_stop]
        
        # strip out extra spaces
        date_str = re.sub(' +', ' ', date_str)
        # strip out "."
        date_str = date_str.replace(".","")
        
        if date_str[0] == ' ':
            date_str = date_str[1:]

        # if there are more than 4 digits, exclude
        list_year = re.findall(r"[0-9]{4}[0-9]", date_str)
        if len(list_year) > 0:
            return None
        
        # strip out "-"
        # may be problematic for some notes but we can adjust this later
        # by taking the EPR date instead
        date_str = date_str.replace("-","")
        
        # exclude things like 26 Jul 2017 1545-1
        list_year = re.findall(r"[0-9]{4}", date_str)
        if len(list_year) > 0:
            idx_year = date_str.find( list_year[0] )
            date_str = date_str[ :idx_year+4 ]
        else:
            # if there are no 4 digits for the year, exclude
            return None

        return date_str
    
    else:
        return None    

def extractJobNum( x ):
    """
    Extract job number from the note if possible. This is heuristic 
    and based on trial and error. It is not perfect and all-encompassing.

    Case 1: "job#" string is present
    Case 2: "dictated but not read" string is present

    x: A string representing the clinical note     
    """

    x = x.lower()

    if 'job#:' in x:
    
        # find the index of job#: 
        title_str = 'job#:'
        idx = x.find(title_str)
        title_str_nl = 'job#:\n'
        if x.find(title_str_nl) != -1:
            idx = x.find(title_str_nl)
            title_str = title_str_nl
        # filter to this substring only
        xJob = x[idx+len(title_str):]

        # find the first \n
        idxNL = xJob.find('\n')

        # extract job#
        jobID = str(xJob[:idxNL])
        # remove extra white spaces
        jobID = re.sub(' +', '', jobID)

        return jobID 
    
    elif 'dictated but not read' in x:
        
        jobID = helperExtractJobID_DictatedNotRead(x, 1)

        if jobID == None:
            return jobID
        elif any(chr.isalpha() for chr in jobID):
            jobID = helperExtractJobID_DictatedNotRead(x, 0)
        
        return jobID

def helperExtractJobID_DictatedNotRead(x, first):
    """
    Helper function to extract job number from note if 'dictated but
    not read' string is present.
    
    x: A string representing the clinical note
    first: Boolean indicating whether to search for the first (1) or
           last (0) occurrence of 'dictated but not read'
    """

    # find position index of dictated but not read
    strToSearch = 'dictated but not read'
    if first == 1:
        # first occurrence
        idx = x.find( strToSearch )
    else:
        # last occurrence
        idx = x.rfind( strToSearch )
    # filter to this substring only
    xJob = x[idx:]

    #xJob = xJob[idxNL+1:]
    xJob = xJob[len(strToSearch)+1:]

    # find transcribed by
    endIdx = xJob.find('transcribed by')

    if endIdx == -1:
        return None

    jobID = xJob[:endIdx]
    jobID = jobID.replace("\n","")
    jobID = re.sub(' +', '', jobID)

    # handle special cases
    jobID = jobID.replace("-re-dictation","")
    jobID = jobID.replace("jobid","")
    jobID = jobID.replace("statnote","")
    jobID = jobID.replace("stat","")
    jobID = jobID.replace("job#","")
    jobID = jobID.replace("redictation","")
    jobID = jobID.replace("-redictation","")
    jobID = jobID.replace("-","")

    if jobID == '' or not any(chr.isdigit() for chr in jobID):
        return None
    else:
        return jobID

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

def process_physician( df ):
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

def get_last_updated(jsonDir, filePartNum, procNames):
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

    dfLastUpdated = pd.DataFrame( {'PATIENT_RESEARCH_ID': patientList, 'observation_id': obsIDList, 'lastUpdated': lastUpdatedList} )

    return dfLastUpdated

def get_last_updated_missing_ci_notes(jsonDir, filePartNum, procNames):
    """
        Extract the lastUpdated column from the raw json file since it's not present
        in the processed CSV files. This is only for the missing .CI notes.

        jsonDir: directory where the raw json files are saved
        filePartNum: file part number to be processed
        procNames: list of procedure names of interest
    """
    # load the json file
    fileName = f"2Blast_part4_{filePartNum}_clinic_notes.zip"
    filePath = jsonDir + '/' + fileName

    jsonFileName = f'{jsonDir}/2Blast_part4_{filePartNum}_clinic_notes.json'
    if not os.path.isfile( jsonFileName ):
        os.system(f"unzip {filePath} -d {jsonDir}")
    
    with open( jsonFileName ) as json_file:
        data = json.load(json_file)

    # tabulate patient id, obs id, last updated

    patientList = []
    clinicIDList = []
    lastUpdatedList = []

    for idx in range(len(data)):
        nObs = len(data[idx]['ClinicNotes'])
        for jdx in range(nObs):
            if str(data[idx]['ClinicNotes'][jdx]['ClinicNote']['code']['text']) in procNames:
                patientList.append( data[idx]['PATIENT_RESEARCH_ID'] )
                clinicIDList.append( data[idx]['ClinicNotes'][jdx]['ClinicNote']['_id'] )
                lastUpdatedList.append( data[idx]['ClinicNotes'][jdx]['ClinicNote']['meta']['lastUpdated'] )

    # delete json file
    os.system(f"rm {jsonDir}/2Blast_part4_{filePartNum}_clinic_notes.json")

    dfLastUpdated = pd.DataFrame( {'PATIENT_RESEARCH_ID': patientList, 'clinical_note_id': clinicIDList, 'lastUpdated': lastUpdatedList} )

    return dfLastUpdated