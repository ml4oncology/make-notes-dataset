# make_notes_dataset

> Generate clinical notes and imaging reports dataset from EMR data.

Python and bash scripts to process the unstructured free-text data set extracted by Cancer Digital Intelligence @ UHN into a more user-friendly form. The resulting data set has columns such as medical record number, note type, visit date, note, physician name, procedure type, etc.


Author: Wayne Uy, PhD

## Notebook description

This is a brief description of the notebooks in this repository.

* 1.0-EDA-duplicates.ipynb 
   - Calculate statistics on duplicity of clinical notes and try to use job number to clean duplicity.
* 1.1-EDA-missing-notes.ipynb
   - Obtain random sample of notes between January 1, 2008 and February 28, 2018 to calculate statistics on missingness with respect to EPR.
* 1.2-EDA-plot-counts.ipynb
   - Produce plots to validate counts of clinical notes in the dataset.

## Procedure for cleaning the clinical notes data set

* Visit date: Use date extracted from the clinical note, if possible. Otherwise, use EPR date. If extracted date is out of bounds, use EPR date instead. In general, the date extracted from the clinical note precedes the EPR date.

* Duplicates: Only drop duplicate clinical notes if job number can be extracted. For clinical notes with the same procedure name and same job number, only retain the clinical note with the most recent last updated date.

* Filtering patients to study period: Drop all records outside the study period. Drop patients whose first visit is outside the study period.

* For all other processing pipelines in the code, the approach is via trial and error. It is an iterative process. Process the notes, manually inspect processed notes for a small sample and compare with EPR/EPIC, apply pipeline fixes, then repeat.

## Extraction

Before processing the notes, raw CSV and JSON files must be extracted from their zipped archives. This is done separately for observation and clinic note archives. Any unzipped CSV files are converted to Parquet format during extraction.

The available data pull dates are 2024-06-04 and 2025-01-08. Run `scripts/extract/extract_zip.sh` with the appropriate pull date:

```bash
./scripts/extract/extract_zip.sh 2024-06-04
# or
./scripts/extract/extract_zip.sh 2025-01-08
```

The last updated date column must also be extracted from the JSON files. For a given data pull date, run:

```bash
./scripts/extract/build_last_updated.sh <data_pull_date> observation
./scripts/extract/build_last_updated.sh <data_pull_date> clinic
```

This date column will be used as a filler for unavailable visit dates.

## Notes pipeline

The unstructured data resides in 2 directory types, ```observation``` and ```clinic notes``` directory. Both of these directories contain notes despite the name.

The consultation notes reside in both directories while imaging reports only resides in the ```observation``` directory. For a given data pull date, run:

```bash
./scripts/notes_pipeline/process_notes.sh <data_pull_date> observation
./scripts/notes_pipeline/process_notes.sh <data_pull_date> clinic
```

Make sure that you request a high memory node as the above pipeline aggregates multiple parquet files to build a unified parquet file for consultation notes in ```observation``` directory, a unified parquet file for consultation notes in ```clinic notes``` directory, and a unified parquet files for imaging reports.

Then, run the following:

```bash
./scripts/notes_pipeline/merge_clean_notes.sh <data_pull_date>
```

to aggregate and clean the consultation notes from both directory types and to clean the imaging reports.

## De-identification

The de-identification pipeline in this repository uses the [Robust DeID model](https://github.com/obi-ml-public/ehr_deidentification) from the [obi-ml-public/ehr_deidentification](https://github.com/obi-ml-public/ehr_deidentification) package. The model has been modified and packaged as an Apptainer image for use on the H4H Cluster at UHN.

Robust DeID removes protected health information (PHI) from clinical text using a RoBERTa-based named entity recognition (NER) model. Age and dates are retained; instead, words are tagged according to their PHI entity type and replaced accordingly.

The pipeline assumes the input dataset contains:
* A patient identifier column (e.g. `PATIENT_RESEARCH_ID` or `mrn`)
* A note text column (e.g. `clinical_notes` or `note`)

### Running the pipeline

1. **Run de-identification** — execute `scripts/main_deid.sh`, which splits the notes dataset into chunks and submits each to the cluster for GPU-accelerated de-identification:

```bash
./scripts/deid/main_deid.sh <data_pull_date>
```

2. **Merge results** — run `scripts/merge_deid_notes.sh` to merge the de-identified dataframe parts back into a single file:

```bash
./scripts/deid/merge_deid_notes.sh <data_pull_date>
```
