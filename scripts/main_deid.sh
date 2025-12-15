#!/bin/bash
set -e

# Input variables

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <data_pull_date>"
    exit 1
fi

data_pull_date="$1"

if [[ $data_pull_date == "2024-06-04" ]]; then
  # old pull
  data_dir=/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04
  df_name=merged_processed_cleaned_clinical_notes_medonc_only.parquet.gzip

elif [[ $data_pull_date == "2025-01-08" ]]; then
  # new pull
  data_dir=/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2025-01-08
  df_name=merged_processed_cleaned_clinical_notes_medonc_only_epic_records_only.parquet.gzip

else
    echo "Invalid data_pull_date: $data_pull_date"
    exit 1
fi

chunk_size=500

# Step 1: Split the dataframe
echo "Splitting dataframe..."
split_files=$(python3 ../src/split_dataframe.py "$data_dir" "$df_name" "$chunk_size")

# Step 2: Create output directories
mkdir -p logs

# Step 3: Submit jobs
echo "Submitting jobs..."
for f in $split_files; do
  df_name=$(basename "$f")
  sbatch job_template_deid.sh "$data_dir/splits" "$df_name"
done

echo "All jobs submitted."
