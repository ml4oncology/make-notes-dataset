import os
import argparse
import pandas as pd
from glob import glob

def merge_deid_dataframes(deid_dir, df_name):
    """
    Merge the de-identified dataframes (deid_<base>_part_x.parquet.gzip) for a
    single source dataframe into one file. df_name is the source dataframe file
    name (e.g. merged_pe_dvt_imaging_report.parquet.gzip) whose parts to merge;
    the base name is derived by stripping the extension.
    The merged dataframe is saved in the same directory as deid_<base>.parquet.gzip.
    """
    # Derive base name (strip .parquet.gzip) the same way split_dataframe.py does
    base = os.path.splitext(os.path.splitext(df_name)[0])[0]

    # Find all part files for this dataframe
    pattern = os.path.join(deid_dir, f"deid_{base}_part_*.parquet.gzip")
    part_files = sorted(glob(pattern))
    if not part_files:
        raise FileNotFoundError(f"No files matching '{pattern}' found in {deid_dir}")

    output_path = os.path.join(deid_dir, f"deid_{base}.parquet.gzip")

    # Load and merge all parts
    print(f"Found {len(part_files)} parts for {base}")
    dfs = [pd.read_parquet(f) for f in part_files]
    merged_df = pd.concat(dfs, ignore_index=True)

    # Save merged dataframe
    merged_df.to_parquet(output_path, compression="gzip")
    print(f"Merged dataframe saved to {output_path} ({len(merged_df):,} rows)")

def main():
    parser = argparse.ArgumentParser(
        description="Merge de-identified dataframe parts (deid_<base>_part_x.parquet.gzip) for a single source dataframe into one file."
    )
    parser.add_argument("deid_dir", type=str, help="Directory containing deid_<base>_part_x.parquet.gzip files")
    parser.add_argument("df_name", type=str, help="Source dataframe file name whose de-identified parts to merge (e.g. merged_pe_dvt_imaging_report.parquet.gzip)")
    args = parser.parse_args()

    merge_deid_dataframes(args.deid_dir, args.df_name)

if __name__ == "__main__":
    main()
