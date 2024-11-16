import os
import zipfile
import pandas as pd
import argparse
import shutil

def extract_zip(zip_directory, save_directory):
    """Extract all zip files in zip_directory to save_directory. Converts
    csv files of interest to parquet.gzip.
    Args:
        zip_directory: path to directory of zip files
        save_directory: path to directory to save parquet.gzip files
    """

    # Ensure the output directory exists
    os.makedirs(save_directory, exist_ok=True)

    # Iterate over all zip files in the specified directory
    for filename in os.listdir(zip_directory):
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
                    # Read the CSV file and convert to Parquet
                    df = pd.read_csv(unzipped_file_path)
                    parquet_file_name = unzipped_file.replace('.csv', '.parquet.gzip')
                    parquet_file_path = os.path.join(save_directory, parquet_file_name)

                    # if Observations.ProcCode is in df.columns, change type
                    cols = [
                        'Observations.ProcCode', 
                        'Observations.Observation.attr.procCode', 
                        'Observations.Observation.component.code.coding.0.code'
                    ] + [f'Observations.Observation.component.extension.{num}.valueString' for num in [3, 4, 6, 7, 8]]
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
    args = parser.parse_args()

    extract_zip(args.zip_directory, args.save_directory)
