import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math

def mergePatientListJSON(dataDir, saveDir, filePartMin, filePartMax):
    """
    Merge list of patients and their corresponding json file part number.

    dataDir: directory path where the processed csv files of patient ids per file number are saved
    saveDir: directory path where merged csv file will be saved
    filePartMin: minimum file part number of files to be merged
    filePartMax: maximum file part number of files to be merged
    """

    mergedPatientList = []
    for ctr in range(filePartMin, filePartMax + 1):
        # load dataframe
        dfTemp = pd.read_csv( f"{dataDir}/dfPatientListJSON_{ctr}.csv", index_col = 0 )
        mergedPatientList.append( dfTemp )

    mergedPatient = pd.concat( mergedPatientList )

    mergedPatient.to_csv(f'{saveDir}/merged_patient_list_JSON.csv')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartMin", help = "file part number minimum", type = int) # minimum file part number
    parser.add_argument("filePartMax", help = "file part number maximum", type = int) # maximum file part number
    args = parser.parse_args()

    mergePatientListJSON( args.dataDir, args.saveDir, args.filePartMin, args.filePartMax )
