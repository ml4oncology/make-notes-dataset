import numpy as np
import pandas as pd
import os
import argparse
from pathlib import Path
import json
import math

def dropSamplesOutsideStudyDate(dataDir, saveDir, startDate, endDate):
    """
    Drop data outside the study date. We only consider patients whose very first visit falls after
    the start date. We drop any record after the end date.

    dataDir: directory path where the clean merged processed csv file is saved
    saveDir: directory path where the clean merged processed csv file filtered by study date will be saved
    startDate: start date (yyyy-mm-dd) of study
    endDate: end date (yyyy-mm-dd) of study 
    """

    mergedNotes = pd.read_parquet(f'{dataDir}/merged_processed_cleaned_clinicalNotes.parquet.gzip', engine='pyarrow', use_nullable_dtypes = True)

    # sort by processed_date and group by MRN
    mergedNotes.sort_values(by='processed_date', inplace=True)

    # obtain the first entry for each MRN
    dfFirstVisit = mergedNotes.groupby(['MRN']).first().reset_index()

    # find the MRNs with first visit date on or after the start date
    MRNAfterStudyStart = dfFirstVisit.loc[ dfFirstVisit['processed_date'] >= startDate ]['MRN'].tolist()
    filteredNotes = mergedNotes.loc[ mergedNotes['MRN'].isin(MRNAfterStudyStart) ].copy()

    # remove any records after the end date
    filteredNotes = filteredNotes.loc[ filteredNotes['processed_date'] <= endDate ]

    # print how many records were dropped
    print("Number of records dropped: ", mergedNotes.shape[0] - filteredNotes.shape[0])

    # assert that the dates are between the start and end dates
    assert sum( filteredNotes['processed_date'].between( startDate, endDate ) ) == filteredNotes.shape[0], "Some visit dates are outside the study period."

    # save clean merged processed csv file filtered by study date
    filteredNotes.to_parquet(f'{saveDir}/merged_processed_cleaned_clinicalNotes_{startDate}_{endDate}.parquet.gzip', compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataDir", help = "data directory", type = str) # data directory
    parser.add_argument("saveDir", help = "save directory", type = str) # save directory
    parser.add_argument("startDate", help = "start date yyyy-mm-dd", type = str) # start date
    parser.add_argument("endDate", help = "end date yyyy-mm-dd", type = str) # end date
    args = parser.parse_args()

    dropSamplesOutsideStudyDate( args.dataDir, args.saveDir, args.startDate, args.endDate )
