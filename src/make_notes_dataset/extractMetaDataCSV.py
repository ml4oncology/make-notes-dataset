import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math

def extractMetaDataCSV(dataDir, saveDir, filePartNum):
    """
    Extract meta data from raw csv files for EDA and to understand structure of 
    notes dataset.

    dataDir: directory path of raw csv files
    saveDir: directory path for saving
    filePartNum: file part number of clinical notes data set
    """

    fileName = f"2Blast_part4_{filePartNum}_results_with_status_dates-output.zip"
    filePath = dataDir + '/' + fileName
    filePath = Path( filePath )

    # unzip file
    os.system(f"unzip {filePath} -d {dataDir}")

    # unzip file
    csvFilePath = dataDir + '/' + f"2Blast_part4_{filePartNum}_results_with_status_dates.csv"
    if not os.path.isfile( csvFilePath ):
        os.system(f"unzip {filePath} -d {dataDir}")

    df = pd.read_csv( csvFilePath )

    # count how many patients
    nPatients = len( df['PATIENT_RESEARCH_ID'].unique() )

    # save number of patients
    np.save(f"{saveDir}/nPatient_{filePartNum}.npy", nPatients)

    # extract only procedures of interest
    procNames = ['Letter', 'Consultation Note', 'Communication Note', 'Radiation Therapy Note',\
                        'OR Procedure/Notes', 'Clinic Note', 'Telephone Advice', 'History & Physical Note',\
                            'Clinic Note (Non-dictated)', 'Discharge Summary',\
                                'Unscheduled Discharge Summary', 'Operative Note',\
                                     'Progress Notes', 'Letters', 'Consultation Report']
    procNames = [x.lower() for x in procNames]
    dfSub = df.loc[ df['Observations.ProcName'].str.lower().isin( procNames ) ].copy()

    # count how many patients under restricted procedures
    nPatientsTopProc = len( dfSub['PATIENT_RESEARCH_ID'].unique() )

    # save number of patients under restricted procedures
    np.save(f"{saveDir}/nPatientTopProc_{filePartNum}.npy", nPatientsTopProc)

    # go over each column and save longest string entry
    # this is to locate the column where notes data are stored
    colName = []
    longestString = []
    for col in dfSub.columns:
        colName.append( col )
        # find values
        colValues = dfSub[col].values
        # find index of longest string
        idxMax = np.array([len(str(x)) for x in colValues]).argmax()
        # find longest string
        longestString.append( colValues[ idxMax ] )
    dfLongestStringPerCol = pd.DataFrame( {'colname': colName, 'longestString': longestString } )

    # save dataframe of longest string
    dfLongestStringPerCol.to_csv( f"{saveDir}/longestStringPerCol_{filePartNum}.csv" )

    # perform some checks
    print(f"Part number is {filePartNum}")

    # Check 1
    # check that 'Observations.Observation.component.code.coding.0.display' and 'Observations.Observation.component.code.text' are both not null
    check_display_text = sum( (dfSub['Observations.Observation.component.code.coding.0.display'].notnull() & dfSub['Observations.Observation.component.code.text'].notnull() ) ) 
    if check_display_text > 0:
        print("first check failed")
    
    # save the unique values of 'Observations.Observation.component.code.coding.0.code'
    unique_coding0code = list( dfSub['Observations.Observation.component.code.coding.0.code'].unique() )

    # save list of unique status
    with open(f"{saveDir}/uniquecoding0code_{filePartNum}.json", 'w') as f:
        json.dump( unique_coding0code, f ) 

    # Check 2
    # find all textualReport in 'Observations.Observation.component.code.coding.0.code'
    dfExtract = dfSub[['Observations.Observation.component.code.coding.0.display', 'Observations.Observation.component.code.coding.0.code', 'Observations.Observation.component.code.text']].copy()
    maskTextualReport = dfExtract['Observations.Observation.component.code.coding.0.code'] == 'textualReport'
    uniqueDisplayList = list( dfExtract.loc[ maskTextualReport ]['Observations.Observation.component.code.coding.0.display'].unique() )
    uniqueTextList = list( dfExtract.loc[ maskTextualReport ]['Observations.Observation.component.code.text'].unique() )

    if len(uniqueDisplayList) > 1 or uniqueDisplayList[0] != 'textualReport':
        print("second check failed")
        print(uniqueDisplayList)
    if len(uniqueTextList) > 1 or uniqueTextList[0] != 'textualReport' or not math.isnan( uniqueTextList[0] ):
        print("second check failed")
        print(uniqueTextList)
    
    # what is Observations.Observation.component.extension.2.valueString overwriting in Observations.Observation.component.valueString ?
    # the idea is for the contents of the former to be merged with the latter
    notesMask = dfSub['Observations.Observation.component.extension.2.url'] == 'NOTES'
    dfNotes = dfSub.loc[ notesMask, ['Observations.Observation.component.extension.2.valueString', 'Observations.Observation.component.valueString'] ].copy()
    metaDataOverwriteNotesList = list( dfNotes.loc[ ( dfNotes['Observations.Observation.component.extension.2.valueString'].notnull() ) & ( dfNotes['Observations.Observation.component.valueString'].notnull() )  ]['Observations.Observation.component.valueString'].unique() )

    # save list of meta data to be overwritten for notes column
    with open(f"{saveDir}/metaDataOverwriteNotes_{filePartNum}.json", 'w') as f:
        json.dump( metaDataOverwriteNotesList, f ) 

    # Check 3
    # check that extension.2.valuestring is not empty while the meta data in extension.2.url is empty
    check_extension2_valueUrl = sum( dfSub['Observations.Observation.component.extension.2.valueString'].notnull() & dfSub['Observations.Observation.component.extension.2.url'].isnull() )
    if check_extension2_valueUrl > 0:
        print("third check failed")
    
    # check what other meta data in extension.2.url gives notes in extension.2.valueString
    dfExtension2 = dfSub.loc[ ( dfSub['Observations.Observation.component.extension.2.valueString'].notnull() ) & ( dfSub['Observations.Observation.component.extension.2.url'].notnull() ), ['Observations.Observation.component.extension.2.valueString','Observations.Observation.component.extension.2.url'] ].reset_index(drop=True).copy()
    dfExtension2['strLen'] = dfExtension2['Observations.Observation.component.extension.2.valueString'].map( lambda x: len(str(x)) )
    grpbyExtension2url = dfExtension2.loc[ dfExtension2.groupby(['Observations.Observation.component.extension.2.url'])['strLen'].idxmax() ]

    # save csv of longest note per data in extension 2
    grpbyExtension2url.to_csv( f"{saveDir}/Extension2LongestStringPerMeta_{filePartNum}.csv" )

    # if there are missing notes, check these 2 assumptions below
    # also, go over each column and find max length. this will help us check if notes data is stored in other columns
    # check if meta data = value such as medical records report. check row in processed data set to see that it is not empty

    dfSub['component_descriptor'] = dfSub['Observations.Observation.component.code.text'].copy()
    dfSub.loc[dfSub['Observations.Observation.component.code.coding.0.display'].notnull(), 'component_descriptor'] = \
        dfSub['Observations.Observation.component.code.coding.0.display'].loc[dfSub['Observations.Observation.component.code.coding.0.display'].notnull()]

    notes_mask = ( dfSub['Observations.Observation.component.extension.2.url'] == 'NOTES' ) & ( dfSub['Observations.Observation.component.extension.2.url'].notnull() )
    dfSub.loc[ notes_mask, 'Observations.Observation.component.valueString' ] = dfSub['Observations.Observation.component.extension.2.valueString'].loc[ notes_mask ]
    dfSub['lengthText'] = dfSub['Observations.Observation.component.valueString'].astype('str').map( lambda x: len(x) )

    # extract metadata, value, and length
    dfExtractColsInterest = dfSub[['PATIENT_RESEARCH_ID', 'Observations.ProcName', 'component_descriptor', 'Observations.Observation.component.valueString', 'lengthText']].copy()

    # save extracted data
    dfExtractColsInterest.to_csv( f"{saveDir}/metaData_text_{filePartNum}.csv" )

    # delete csv files
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates.csv")
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates-meta.csv")
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates-msgs.csv")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartNum", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    extractMetaDataCSV( args.dataDir, args.saveDir, args.filePartNum )
