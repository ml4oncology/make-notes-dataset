#!/usr/bin/env python3
import pandas as pd
import sys
import os

def split_dataframe(data_dir, df_name, chunk_size=200):
    df_path = os.path.join(data_dir, df_name)
    df = pd.read_parquet(df_path)

    fname = os.path.splitext(os.path.splitext(df_name)[0])[0]  # remove .parquet.gzip
    out_dir = os.path.join(data_dir, "splits")
    os.makedirs(out_dir, exist_ok=True)

    n_chunks = (len(df) + chunk_size - 1) // chunk_size
    for i in range(n_chunks):
        start, end = i * chunk_size, (i + 1) * chunk_size
        df_part = df.iloc[start:end]
        out_name = f"{fname}_part_{i+1}.parquet.gzip"
        out_path = os.path.join(out_dir, out_name)
        df_part.to_parquet(out_path, compression="gzip")
        print(out_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python split_dataframe.py <data_dir> <df_name> [chunk_size]")
        sys.exit(1)
    data_dir, df_name = sys.argv[1], sys.argv[2]
    chunk_size = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    split_dataframe(data_dir, df_name, chunk_size)
