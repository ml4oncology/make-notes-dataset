import os
import zipfile
import pandas as pd
import argparse
import shutil
import logging
import math
import csv
import re
import sys
import ctypes as ct
logging.basicConfig(
    level=logging.INFO         # Log level (you can adjust it to INFO, DEBUG, etc.)
)
logger = logging.getLogger(__name__)

def extract_zip(zip_directory, save_directory, batch_index=None, total_batches=None):
    """Extract all zip files in zip_directory to save_directory. Converts
    csv files of interest to parquet.gzip.
    Args:
        zip_directory: path to directory of zip files
        save_directory: path to directory to save parquet.gzip files
        batch_index (optional): The current batch index (0-based).
        total_batches (optional): Total number of batches.
    """

    # Ensure the output directory exists
    os.makedirs(save_directory, exist_ok=True)

    # Get a sorted list of all zip files
    zip_files = sorted([f for f in os.listdir(zip_directory) if f.endswith('.zip')])

    # If batch processing is enabled, determine the files for this batch
    if batch_index is not None and total_batches is not None:
        num_files = len(zip_files)
        batch_size = math.ceil(num_files / total_batches)
        start_idx = batch_index * batch_size
        end_idx = min(start_idx + batch_size, num_files)

        if start_idx >= num_files:
            logger.info(f"Batch {batch_index} has no files to process.")
            return

        zip_files = zip_files[start_idx:end_idx]
        logger.info(f"Processing batch {batch_index + 1}/{total_batches}: {len(zip_files)} files")

    else:
        logger.info(f"Processing all {len(zip_files)} zip files")

    # Iterate over all zip files in the specified directory
    for filename in zip_files:

        logger.info(f"Processing {filename}")

        if filename.endswith('.zip'):
            zip_file_path = os.path.join(zip_directory, filename)

            # Unzip the file
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(zip_directory)

            # Iterate over the unzipped files
            for unzipped_file in zip_ref.namelist():
                unzipped_file_path = os.path.join(zip_directory, unzipped_file)

                # Check if the file name contains 'meta' or 'msgs'
                if 'meta' in unzipped_file or 'msgs' in unzipped_file:
                    os.remove(unzipped_file_path)  # Delete the file

                elif unzipped_file.endswith('.csv'):
                    # fix any problems with the csv file
                    cleaned_output_file = unzipped_file_path.replace(".csv", "_cleaned.csv")

                    # Open input file for reading and output file for writing
                    with open(unzipped_file_path, "r", newline="", encoding="utf-8") as infile, \
                        open(cleaned_output_file, "w", newline="", encoding="utf-8") as outfile:

                        reader = csv.reader(infile)
                        writer = csv.writer(outfile)

                        # Read the header
                        header = next(reader)
                        writer.writerow(header)

                        clinic_note = 1
                        notes_col1 = "Observations.Observation.component.valueString"
                        notes_col2 = "Observations.Observation.component.extension.2.valueString"

                        if notes_col1 in header:
                            clinic_note = 0

                        if clinic_note == 0:
                            col_indexes = [header.index(notes_col1), header.index(notes_col2)]

                            csv.field_size_limit(int(ct.c_ulong(-1).value // 2))
                            # Process the rows
                            for row in reader:
                                for col_index in col_indexes:
                                    if col_index < len(row):
                                        row[col_index] = re.sub(r"\\\.br\\", "", row[col_index])
                                        if row[col_index].endswith("\\"):
                                            # row[col_index] = row[col_index][:-1]  # Remove trailing slash
                                            row[col_index] = row[col_index].rstrip("\\")
                                writer.writerow(row)
                        else:
                            cleaned_output_file = unzipped_file_path

                    try:
                        df = pd.read_csv(cleaned_output_file, low_memory=False, quotechar='"', escapechar='\\')
                    except:
                        logger.error(f"Error reading {cleaned_output_file}")
                        df = pd.read_csv(cleaned_output_file, low_memory=False, quotechar='"', escapechar='\\', on_bad_lines='warn')
                            
                    parquet_file_name = unzipped_file.replace('.csv', '.parquet.gzip')
                    parquet_file_path = os.path.join(save_directory, parquet_file_name)

                    # if Observations.ProcCode is in df.columns, change type
                    cols = [
                        'Observations.ProcCode', 
                        'Observations.Observation.attr.procCode', 
                        'Observations.Observation.component.code.coding.0.code',
                        'ClinicNotes.ClinicNote.identifier.0.value',
                        'ClinicNotes.ClinicNote.code.coding.0.code'
                    ] + [
                        f'Observations.Observation.component.extension.{num}.valueString' for num in [3, 4, 6, 7, 8]
                    ] + [
                        f'ClinicNotes.ClinicNote.attr.msgid.{num}' for num in [4, 5, 6, 7, 8, 9]
                    ] + [
                        f'ClinicNotes.ClinicNote.{val}.identifier.value' for val in ['encounter', 'subject', 'assessor']
                    ]

                    for col in cols:
                        if col in df.columns:
                            df[col] = df[col].astype(str)

                    # Save the DataFrame to Parquet format
                    df.to_parquet(parquet_file_path, compression='gzip', index=False)

                    # Optionally, delete the original CSV after conversion
                    os.remove(unzipped_file_path)

                elif unzipped_file.endswith('.json'):
                    # Move the JSON file to the output directory
                    shutil.move(unzipped_file_path, os.path.join(save_directory, unzipped_file))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_directory", help="path of zip files", type=str)  # path of zip files
    parser.add_argument("save_directory", help="path of save directory", type=str)  # path of save directory
    parser.add_argument("--batch_index", type=int, default=None, help="Index of the batch (0-based, optional)")
    parser.add_argument("--total_batches", type=int, default=None, help="Total number of batches (optional)")
    args = parser.parse_args()

    extract_zip(args.zip_directory, args.save_directory, args.batch_index, args.total_batches)
