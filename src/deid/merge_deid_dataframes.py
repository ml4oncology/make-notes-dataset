import os
import re
import argparse
import pandas as pd
from glob import glob

def merge_deid_dataframes(deid_dir):
    """
    Merge all de-identified dataframes (deid_*_part_x.parquet.gzip) in the given directory.
    The merged dataframe is saved in the same directory as deid_*.parquet.gzip.
    """
    # Find all part files
    part_files = sorted(glob(os.path.join(deid_dir, "deid_*_part_*.parquet.gzip")))
    if not part_files:
        raise FileNotFoundError(f"No files matching 'deid_*_part_*.parquet.gzip' found in {deid_dir}")

    # Extract base name pattern (e.g., deid_sampled_200 from deid_sampled_200_part_1.parquet.gzip)
    match = re.match(r"(deid_.+?)_part_\d+\.parquet\.gzip", os.path.basename(part_files[0]))
    if not match:
        raise ValueError(f"Unexpected filename format: {os.path.basename(part_files[0])}")

    base_name = match.group(1)
    output_path = os.path.join(deid_dir, f"{base_name}.parquet.gzip")

    # Load and merge all parts
    print(f"Found {len(part_files)} parts for {base_name}")
    dfs = [pd.read_parquet(f) for f in part_files]
    merged_df = pd.concat(dfs, ignore_index=True)

    # Save merged dataframe
    merged_df.to_parquet(output_path, compression="gzip")
    print(f"Merged dataframe saved to {output_path} ({len(merged_df):,} rows)")

def main():
    parser = argparse.ArgumentParser(
        description="Merge de-identified dataframe parts (deid_*_part_x.parquet.gzip) into a single file."
    )
    parser.add_argument("deid_dir", type=str, help="Directory containing deid_*_part_x.parquet.gzip files")
    args = parser.parse_args()

    merge_deid_dataframes(args.deid_dir)

if __name__ == "__main__":
    main()
