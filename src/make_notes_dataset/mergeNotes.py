import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math

def mergeNotes(dataDir, saveDir, filePartMin, filePartMax):
    """
    Merge processed clinical notes csv into a parquet file for compression.

    dataDir: directory path where the processed csv files are saved
    saveDir: directory path where merged parquet file will be saved
    filePartMin: minimum file part number of files to be merged
    filePartMax: maximum file part number of files to be merged
    """

    mergedNotesList = []
    for ctr in range(filePartMin, filePartMax + 1):
        # load dataframe
        dfTemp = pd.read_csv( f"{dataDir}/processedClinicalNotes_{ctr}.csv", index_col = 0 )
        mergedNotesList.append( dfTemp )

    mergedNotes = pd.concat( mergedNotesList )
    # mergedNotes['e_mail_address'] = mergedNotes['e_mail_address'].astype(str)

    mergedNotes['visitDate'] = pd.to_datetime( mergedNotes['visitDate'], utc=True )
    mergedNotes['lastUpdated'] = pd.to_datetime( mergedNotes['lastUpdated'].apply( lambda x: x.replace('T', ' ').replace('Z','')[:19] ),\
                                                 utc=True, format='%Y-%m-%d %H:%M:%S' )

    mergedNotes.to_parquet(f'{saveDir}/merged_processed_clinicalNotes.parquet.gzip', compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("filePartMin", help = "file part number minimum", type = int) # minimum file part number
    parser.add_argument("filePartMax", help = "file part number maximum", type = int) # maximum file part number
    args = parser.parse_args()

    mergeNotes( args.dataDir, args.saveDir, args.filePartMin, args.filePartMax )
