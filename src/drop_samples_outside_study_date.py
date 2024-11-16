import pandas as pd
import argparse
import logging

logger = logging.getLogger(__name__)

def drop_samples_outside_study_date(data_dir, save_dir, start_date, end_date):
    """
    Drop data outside the study date. We only consider patients whose very first visit falls after
    the start date. We drop any record after the end date.

    data_dir: directory path where the clean merged processed csv file is saved
    save_dir: directory path where the clean merged processed csv file filtered by study date will be saved
    start_date: start date (yyyy-mm-dd) of study
    end_date: end date (yyyy-mm-dd) of study 
    """

    merged_notes = pd.read_parquet(f'{data_dir}/merged_processed_cleaned_clinical_notes.parquet.gzip', engine='pyarrow', use_nullable_dtypes=True)

    # sort by processed_date and group by MRN
    merged_notes.sort_values(by='processed_date', inplace=True)

    # obtain the first entry for each MRN
    df_first_visit = merged_notes.groupby(['mrn']).first().reset_index()

    # find the MRNs with first visit date on or after the start date
    mrn_after_study_start = df_first_visit.loc[df_first_visit['processed_date'] >= start_date]['mrn'].tolist()
    filtered_notes = merged_notes.loc[merged_notes['mrn'].isin(mrn_after_study_start)].copy()

    # remove any records after the end date
    filtered_notes = filtered_notes.loc[filtered_notes['processed_date'] <= end_date]

    # print how many records were dropped
    logger.info(f"Number of records dropped: {merged_notes.shape[0] - filtered_notes.shape[0]}")

    # assert that the dates are between the start and end dates
    assert sum(filtered_notes['processed_date'].between(start_date, end_date)) == filtered_notes.shape[0], "Some visit dates are outside the study period."

    # save clean merged processed csv file filtered by study date
    filtered_notes.to_parquet(f'{save_dir}/merged_processed_cleaned_clinical_notes_{start_date}_{end_date}.parquet.gzip', compression='gzip', index=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help="data directory", type=str)  # data directory
    parser.add_argument("save_dir", help="save directory", type=str)  # save directory
    parser.add_argument("start_date", help="start date yyyy-mm-dd", type=str)  # start date
    parser.add_argument("end_date", help="end date yyyy-mm-dd", type=str)  # end date
    args = parser.parse_args()

    drop_samples_outside_study_date(args.data_dir, args.save_dir, args.start_date, args.end_date)
