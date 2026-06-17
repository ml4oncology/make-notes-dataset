# make_notes_dataset

> Generate clinical notes dataset from EMR data.

Python and bash scripts to process the clinical notes data set extracted by CDI into a more usable form.


## Notebook description

This is a brief description of the notebooks in this repository.

* 0.EDA-checkMetaData.ipynb 
   - Investigate the column names, their contents, and the relevant metadata with clinical notes in the processed CSV files provided by CDI.
* 1.validation-DateInNote_vs_EPRdate.ipynb
   - Extract the date of visit from the clinical note, if possible, and compare it with the EPR date.
* 1.1-wy-EDA-missing-notes.ipynb
   - Obtain random sample of notes between January 1, 2008 and February 28, 2018 to calculate statistics on missingness with respect to EPR.
* 1.2-wy-EDA-plot-counts.ipynb
   - Produce plots to validate counts of clinical notes in the dataset.

## Procedure for cleaning the data set

* Visit date: Use date extracted from the clinical note, if possible. Otherwise, use EPR date. If extracted date is out of bounds, use EPR date instead. In general, the date extracted from the clinical note precedes the EPR date.

* Duplicates: Only drop duplicate clinical notes if job number can be extracted. For clinical notes with the same procedure name and same job number, only retain the clinical note with the most recent last updated date.

* Filtering patients to study period: Drop all records outside the study period. Drop patients whose first visit is outside the study period

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
