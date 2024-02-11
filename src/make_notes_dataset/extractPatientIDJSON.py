import json
import numpy as np
import pandas as pd
import os
import argparse

def extractPatientIDJSON( dataDir, saveDir, filePartNum ):
    """
    Extract patient list per json file.

    dataDir: directory path of raw json files
    saveDir: directory path for saving
    filePartNum: file part number of clinical notes data set
    """

    fileName = f"2Blast_part4_{filePartNum}_results_with_status_dates.zip"
    filePath = dataDir + '/' + fileName

    # unzip file
    JSONFilePath = dataDir + '/' + f"2Blast_part4_{filePartNum}_results_with_status_dates.json"
    if not os.path.isfile( JSONFilePath ):
        os.system(f"unzip {filePath} -d {dataDir}")

    # load json file
    with open(f'{dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates.json') as json_file:
        data = json.load(json_file)

    # patient list in this file
    patientList = []

    for idx in range(len(data)):
        patientList.append( data[idx]['PATIENT_RESEARCH_ID'] )

    print(f"Part number is {filePartNum}")
    if len( set( patientList ) ) != len( patientList ):
        print("check failed")

    dfPatientList = pd.DataFrame( { "PATIENT_RESEARCH_ID": patientList, "filePartNum": filePartNum } )

    # save dataframe
    dfPatientList.to_csv( f"{saveDir}/dfPatientListJSON_{filePartNum}.csv" )

    # delete json file
    os.system(f"rm {dataDir}/2Blast_part4_{filePartNum}_results_with_status_dates.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartNum", help = "file part number", type = int) # file part number
    args = parser.parse_args()

    extractPatientIDJSON( args.dataDir, args.saveDir, args.filePartNum )
