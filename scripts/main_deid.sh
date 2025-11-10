#!/bin/bash
set -e

# Input variables
# old pull
data_dir=/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2024-06-04
df_name=merged_processed_cleaned_clinical_notes_medonc_only.parquet.gzip

# new pull
# data_dir=/cluster/projects/gliugroup/2BLAST/data/processed/clinical_notes/data_pull_2025-01-08
# df_name=merged_processed_cleaned_clinical_notes_medonc_only_epic.parquet.gzip

chunk_size=200

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
