"""
process_notes.py  —  Polars-accelerated rewrite
================================================
Run ONE job per note type for a given data-pull date:

    python process_notes.py <data_dir> <json_dir> <save_dir> <mrn_file>
                            <clinic_notes_dir> <file_glob>
                            <file_name_template> <upper_limit>

    e.g. (observation):
        python process_notes.py \
            /cluster/.../observation_parquet \
            /cluster/.../observation_json \
            /cluster/.../2025-01-08/obs_notes_parts \
            /cluster/.../mrn_map_2Blast_part5.csv \
            0 \
            "2Blast_part5_*_observations.parquet.gzip" \
            "2Blast_part5_file-part-num_observations.parquet.gzip" \
            1775

    e.g. (clinic):
        python process_notes.py \
            /cluster/.../clinic_notes_parquet \
            /cluster/.../clinic_notes_json \
            /cluster/.../2025-01-08/clinic_notes_parts \
            /cluster/.../mrn_map_2Blast_part5.csv \
            1 \
            "2Blast_part5_*_clinic_notes.parquet.gzip" \
            "2Blast_part5_file-part-num_clinic_notes.parquet.gzip" \
            1775

Outputs (all in <save_dir>):
  observation mode:
    processed_observation_notes.parquet.gzip
    processed_pe_dvt_imaging_report.parquet.gzip
  clinic mode:
    processed_clinic_notes.parquet.gzip
"""

import sys
import os
import re
import glob
import logging
import argparse

import pandas as pd
import polars as pl

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

from util import (
    process_date,
    process_physician,
    get_last_updated_obs_notes,
    get_last_updated_clinic_ci_notes,
    extract_header,
)

from constants import (
    PROCEDURE_NAMES_OF_INTEREST_EPR,
    PROCEDURE_NAMES_OF_INTEREST_EPIC,
    NOTES_METADATA,
    OTHER_METADATA,
    PATIENT_ID_PATTERN,
    AUTHOR_TYPES_OF_INTEREST,
    IMAGING_PROCEDURE_NAMES,
    IMAGING_METADATA,
    IMAGING_NOTES_METADATA,
)

sys.path.insert(1, "/cluster/projects/gliugroup/2BLAST/data/info")
from phys_names import aliasDictionary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text cleaning helpers  (unchanged — row-level Python UDFs)
# ---------------------------------------------------------------------------

def remove_bmk_lines(text: str) -> str:
    """Remove leading/trailing 'bmk' lines and strip non-blank lines."""
    text = text.rstrip()
    lines = text.splitlines()
    # Remove first line if it's just 'bmk' (with optional whitespace)
    if lines and lines[0].strip() == "bmk":
        lines = lines[1:]
    # Remove last line if it's just 'bmk' (with optional whitespace)
    if lines and lines[-1].strip() == "bmk":
        lines = lines[:-1]
    # Strip leading/trailing spaces from non-blank lines
    return "\n".join(line.strip() if line.strip() else line for line in lines)


def split_metadata_col_clinic(note_text: str):
    """Split a clinic note cell into (meta_data, text_data).

    Expected format: '10060/Report Type: Clinic Note'.
    If the cell is a raw clinic note (contains newlines), returns
    ('clinical_note', note_text).  Falls back to ('undefined', note_text).
    """
    if "\n" in note_text:
        return "clinical_note", note_text

    if "/" in note_text:
        slash_position = note_text.index("/")
        colon_position = note_text.index(":")
        meta_data = note_text[slash_position + 1 : colon_position]
        text_data = note_text[colon_position + 2 :]

        if meta_data[0] == "/" or (len(meta_data) > 1 and meta_data[1] == "/"):
            slash_position = meta_data.index("/")
            meta_data = meta_data[slash_position + 1 :]

        return meta_data, text_data

    return "undefined", note_text


# ---------------------------------------------------------------------------
# Polars helpers — I/O and basic filtering
# ---------------------------------------------------------------------------

def scan_raw_parquet(data_dir: str, file_glob: str) -> pl.LazyFrame:
    """Glob all matching parquet files and return a single LazyFrame.

    String 'None' values are replaced with a true null via a post-scan
    with_columns pass.
    """
    pattern = os.path.join(data_dir, file_glob)
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No parquet files matched: {pattern}")
    logger.info(f"Scanning {len(paths)} parquet files from {data_dir}")

    lf = pl.scan_parquet(paths)

    # Replace the string sentinel 'None' with a true null across String columns only.
    schema = lf.collect_schema()
    str_cols = [name for name, dtype in schema.items() if dtype == pl.String]
    if str_cols:
        lf = lf.with_columns(
            [
                pl.when(pl.col(c) == "None").then(None).otherwise(pl.col(c)).alias(c)
                for c in str_cols
            ]
        )

    return lf


def filter_valid_patient_ids_pl(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Keep rows whose PATIENT_RESEARCH_ID is non-null and matches the pattern."""
    return lf.filter(
        pl.col("PATIENT_RESEARCH_ID").is_not_null()
        & pl.col("PATIENT_RESEARCH_ID").str.contains(PATIENT_ID_PATTERN)
    )


def rename_columns_pl(
    lf: pl.LazyFrame, clinic_notes_dir: bool
) -> tuple[pl.LazyFrame, str, str]:
    """Rename raw column names to standardized names.

    Returns (lf, proc_name_col, visit_id_col).
    """
    if clinic_notes_dir:
        mapping = {
            "ClinicNotes.ClinicNote.note.text": "note_text",
            "ClinicNotes.ClinicNote.date": "note_date",
            "ClinicNotes.ClinicNote.effectiveDateTime": "effective_date_time",
            "ClinicNotes.ClinicNote._id": "clinical_note_id",
            "ClinicNotes.ClinicNote.code.text": "code_text",
            "ClinicNotes.ClinicNote.encounter.reference": "encounter_reference",
        }
        proc_name_col = "code_text"
        visit_id_col = "clinical_note_id"
    else:
        mapping = {
            "Observations.Observation._id": "observation_id",
            "Observations.OccurrenceDateTimeFromOrder": "occurrence_date_time_from_order",
            "Observations.Observation.effectiveDateTime": "effective_date_time",
            "Observations.Observation.component.code.text": "component_code_text",
            "Observations.Observation.component.code.coding.0.display": "component_code_display",
            "Observations.Observation.component.extension.2.url": "component_extension_url",
            "Observations.Observation.component.valueString": "text_data",
            "Observations.Observation.component.extension.2.valueString": "component_extension_value_string",
        }
        proc_name_col = "Observations.ProcName"
        visit_id_col = "observation_id"

    existing = set(lf.collect_schema().names())
    safe_mapping = {k: v for k, v in mapping.items() if k in existing}
    lf = lf.rename(safe_mapping)
    return lf, proc_name_col, visit_id_col


def attach_mrn_pl(lf: pl.LazyFrame, mrn_file: str) -> pl.LazyFrame:
    """Join a PATIENT_RESEARCH_ID → MRN lookup onto the LazyFrame."""
    mrns_pd = pd.read_csv(mrn_file)
    if "RESEARCH_ID" in mrns_pd.columns:
        mrns_pd = mrns_pd.rename(columns={"RESEARCH_ID": "PATIENT_RESEARCH_ID"})
    mrns_pd["PATIENT_RESEARCH_ID"] = mrns_pd["PATIENT_RESEARCH_ID"].astype(str)
    mrns_pd["MRN"] = mrns_pd["MRN"].astype("int64")

    mrn_lf = pl.from_pandas(mrns_pd[["PATIENT_RESEARCH_ID", "MRN"]]).lazy()
    lf = lf.join(mrn_lf, on="PATIENT_RESEARCH_ID", how="left").rename({"MRN": "mrn"})
    return lf


# ---------------------------------------------------------------------------
# Polars helpers — observation metadata creation
# ---------------------------------------------------------------------------

def create_metadata_pl(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Create meta_data and text_data columns for the observation-notes LazyFrame."""
    lf = lf.with_columns(
        pl.when(pl.col("component_code_display").is_not_null())
        .then(pl.col("component_code_display"))
        .otherwise(pl.col("component_code_text"))
        .str.to_lowercase()
        .alias("meta_data")
    ).with_columns(
        pl.when(pl.col("component_extension_url") == "NOTES")
        .then(pl.col("component_extension_value_string"))
        .otherwise(pl.col("text_data"))
        .alias("text_data")
    )

    columns_to_keep = [
        "mrn",
        "PATIENT_RESEARCH_ID",
        "Observations.ProcCode",
        "Observations.ProcName",
        "observation_id",
        "Observations.StatusFromOrder",
        "occurrence_date_time_from_order",
        "Observations.Observation.basedOn.0.reference",
        "Observations.Observation.encounter.reference",
        "Observations.Observation.status",
        "effective_date_time",
        "meta_data",
        "text_data",
    ]
    existing = set(lf.collect_schema().names())
    safe_keep = [c for c in columns_to_keep if c in existing]
    return lf.select(safe_keep)


# ---------------------------------------------------------------------------
# Metadata maps
# ---------------------------------------------------------------------------

def build_metadata_maps():
    """Return (map_notes_meta, map_other_meta) dicts mapping raw metadata labels
    to column-safe names (spaces/hyphens/slashes replaced with underscores)."""
    map_notes_meta = {
        elem: elem.replace(" ", "_").replace("-", "_").replace("/", "_")
        for elem in NOTES_METADATA
    }
    map_other_meta = {
        elem: elem.replace(" ", "_").replace("-", "_").replace("/", "_").replace("'", "_")
        for elem in OTHER_METADATA
    }
    return map_notes_meta, map_other_meta


# ---------------------------------------------------------------------------
# Pivot + dedup (pandas — data is already filtered/small at this point)
# ---------------------------------------------------------------------------

def filter_and_pivot_metadata(
    df: pd.DataFrame,
    map_meta: dict,
    metadata_of_interest: list | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retain only metadata rows of interest and pivot to one-row-per-visit.

    Args:
        df: long-format dataframe with 'meta_data' and 'text_data' columns.
        map_meta: dict mapping raw metadata labels to column-safe names.
        metadata_of_interest: list of raw metadata labels to keep. Defaults to
            NOTES_METADATA + OTHER_METADATA (the clinical-notes set).
    """
    if metadata_of_interest is None:
        metadata_of_interest = NOTES_METADATA + OTHER_METADATA

    df_meta = df.loc[df["meta_data"].isin(metadata_of_interest)].copy()

    if "Observations.ProcCode" in df_meta.columns:
        try:
            df_meta["Observations.ProcCode"] = df_meta["Observations.ProcCode"].astype(int)
        except (ValueError, TypeError):
            df_meta["Observations.ProcCode"] = df_meta["Observations.ProcCode"].astype(str)

    df_meta["meta_data"] = df_meta["meta_data"].map(map_meta)

    cols_to_group_by = [c for c in df_meta.columns if c not in ["meta_data", "text_data"]]
    df_meta[cols_to_group_by] = df_meta[cols_to_group_by].fillna("dummy")
    df_meta["meta_data"] = df_meta["meta_data"].astype(str)
    df_meta["text_data"] = df_meta["text_data"].astype(str)

    pivot_df = df_meta.pivot_table(
        "text_data",
        cols_to_group_by,
        "meta_data",
        aggfunc=lambda x: " ".join(x),
    )
    pivot_df.reset_index(drop=False, inplace=True)
    pivot_df = pivot_df.rename_axis(None, axis=1)

    return pivot_df, df_meta


def deduplicate_pivot(
    pivot_df: pd.DataFrame, df_meta: pd.DataFrame, visit_id_col: str
) -> pd.DataFrame:
    """Heuristically resolve any duplicate rows introduced by pivoting."""
    n_patient_obs = df_meta[['PATIENT_RESEARCH_ID', visit_id_col]].drop_duplicates().shape[0]
    if pivot_df.shape[0] != n_patient_obs:
        logger.info("Warning: duplicate rows after pivoting\n")

    group_1_cols = ['mrn', 'PATIENT_RESEARCH_ID', visit_id_col]
    group_2_cols = [col for col in df_meta.columns if col not in group_1_cols + ['meta_data', 'text_data']]
    group_3_cols = [col for col in pivot_df.columns if col not in group_1_cols + group_2_cols]

    agg_funcs = {col: 'first' for col in group_1_cols}
    agg_funcs.update({
        col: (lambda x: x[x != 'dummy'].iloc[0] if (x != 'dummy').any() else 'dummy')
        for col in group_2_cols
    })
    agg_funcs.update({col: lambda x: x.bfill().iloc[0] for col in group_3_cols})

    pivot_df = pivot_df.groupby(['PATIENT_RESEARCH_ID', visit_id_col], as_index=False).agg(agg_funcs)
    return pivot_df 


# ---------------------------------------------------------------------------
# Clinic-notes specific pre-pivot steps
# ---------------------------------------------------------------------------

def apply_clinic_note_adjustments_pl(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Drop empty notes and compute epr_date."""
    lf = lf.filter(
        pl.col("note_text").is_null()
        | (pl.col("note_text").str.strip_chars().str.len_chars() > 1)
    )
    lf = lf.with_columns(
        pl.coalesce(["note_date", "effective_date_time"]).alias("epr_date")
    )
    return lf


def split_epic_epr_pl(lf: pl.LazyFrame) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Split into EPR (summary null) and EPIC (summary non-null) LazyFrames."""
    lf_epr = lf.filter(pl.col("ClinicNotes.ClinicNote.summary").is_null())
    lf_epic = lf.filter(pl.col("ClinicNotes.ClinicNote.summary").is_not_null())
    return lf_epr, lf_epic


def deduplicate_clinic_metadata(df: pd.DataFrame) -> pd.DataFrame:
    """For clinic notes, de-duplicate physician-level metadata rows and merge
    text values that share the same metadata category."""
    df_other = df.loc[~df["meta_data"].str.lower().isin(OTHER_METADATA)].copy()
    df_phys = df.loc[df["meta_data"].str.lower().isin(OTHER_METADATA)].copy()
    df_phys.drop_duplicates(
        subset=["PATIENT_RESEARCH_ID", "clinical_note_id", "meta_data", "text_data"],
        inplace=True,
    )

    df = pd.concat([df_other, df_phys], axis=0)
    # merge text values if the meta_data is the same
    # this can happen since the note is sometimes split such as
    # 14001/Medical Records Report: Date of Visit: 17 Jan 2019
    # 14001/Medical Records Report: Dear Dr. X:
    group_by_cols = [
        "mrn",
        "PATIENT_RESEARCH_ID",
        "clinical_note_id",
        "code_text",
        "epr_date",
        "encounter_reference",
        "meta_data",
    ]

    df_grouped = (
        df.groupby(group_by_cols)
        .agg(text_data=("text_data", lambda x: "\n".join(x)))
        .reset_index()
    )
    df_grouped["meta_data"] = df_grouped["meta_data"].str.lower()
    return df_grouped


# ---------------------------------------------------------------------------
# Post-pivot pandas steps (shared by both note types)
# ---------------------------------------------------------------------------

def fix_medical_records_report(pivot_df: pd.DataFrame) -> pd.DataFrame:
    """For clinic notes, replace placeholder 'Medical Records Report' values
    with the actual clinical note text where available."""
    mask = (
        (pivot_df["medical_records_report"] == "Medical Records Report")
        & pivot_df["clinical_note"].notna()
    )
    pivot_df.loc[mask, "medical_records_report"] = pivot_df.loc[mask, "clinical_note"]

    mask = pivot_df["medical_records_report"].isna() & pivot_df["clinical_note"].notna()
    pivot_df.loc[mask, "medical_records_report"] = pivot_df.loc[mask, "clinical_note"]
    return pivot_df


def aggregate_notes_columns(
    pivot_df: pd.DataFrame, map_notes_meta: dict, clinic_notes_dir: bool
) -> pd.DataFrame:
    """Merge all individual note columns into a single 'clinical_notes' column."""
    cols_to_agg_master = list(map_notes_meta.values())
    cols_to_agg_local = [c for c in cols_to_agg_master if c in pivot_df.columns]

    if clinic_notes_dir and "clinical_note" in cols_to_agg_local:
        cols_to_agg_local.remove("clinical_note")

    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].astype(str)
    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].replace("nan", "")
    pivot_df[cols_to_agg_local] = pivot_df[cols_to_agg_local].replace("None", "")

    if "medical_records_report" in pivot_df.columns:
        pivot_df.loc[
            pivot_df["medical_records_report"] == "Medical Records Report",
            "medical_records_report",
        ] = ""
    if "note" in pivot_df.columns:
        pivot_df.loc[pivot_df["note"] == "Note", "note"] = ""

    pivot_df["clinical_notes"] = pivot_df[cols_to_agg_local].agg("\n\n".join, axis=1)
    pivot_df.drop(columns=cols_to_agg_local, inplace=True)

    if "clinical_note" in pivot_df.columns:
        pivot_df.drop(columns="clinical_note", inplace=True)

    return pivot_df


def apply_date_corrections(pivot_df: pd.DataFrame, clinic_notes_dir: bool) -> pd.DataFrame:
    """Parse and normalize the visit date column."""
    if clinic_notes_dir:
        pivot_df["date_dictated"] = pd.to_datetime(
            pivot_df["date_dictated"], utc=True, format="mixed"
        )
        pivot_df["epr_date"] = pd.to_datetime(pivot_df["epr_date"], utc=True)
        pivot_df["visit_date"] = pivot_df["date_dictated"].dt.date

        mask = pivot_df["visit_date"].isna() & pivot_df["epr_date"].notna()
        pivot_df.loc[mask, "visit_date"] = pivot_df.loc[mask, "epr_date"].dt.date
    else:
        pivot_df = process_date(pivot_df)
    return pivot_df


def drop_empty_note_rows(
    pivot_df: pd.DataFrame, note_col: str = "clinical_notes"
) -> pd.DataFrame:
    """Remove rows where the note column contains nothing but newlines."""
    pivot_df['new_line_only'] = pivot_df[note_col].apply(
        lambda x: all(char == '\n' for char in x)
    )
    pivot_df = pivot_df.loc[pivot_df['new_line_only'] == False]
    pivot_df.drop('new_line_only', axis=1, inplace=True)
    return pivot_df


# ---------------------------------------------------------------------------
# Last-updated helper — aggregated across all file parts
# ---------------------------------------------------------------------------

def build_last_updated_all_parts(
    json_dir: str,
    file_name_template: str,
    upper_limit: int,
    clinic_notes_dir: bool,
    proc_names: list,
) -> pd.DataFrame:
    """Collect last-updated timestamps for every file part and concatenate.

    Reuses the existing get_last_updated_* util functions unchanged;
    iterates over all part numbers and stacks the results.
    """
    frames = []
    for i in range(upper_limit + 1):
        try:
            if clinic_notes_dir:
                df_part = get_last_updated_clinic_ci_notes(
                    json_dir, i, file_name_template, proc_names
                )
            else:
                df_part = get_last_updated_obs_notes(
                    json_dir, i, file_name_template, proc_names
                )
            if df_part is not None and not df_part.empty:
                frames.append(df_part)
        except Exception as exc:
            logger.warning(f"get_last_updated failed for part {i}: {exc}")

    if not frames:
        logger.warning("No last_updated data found — returning empty DataFrame.")
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# EPIC notes pipeline (pandas — row-level logic, unchanged from original)
# ---------------------------------------------------------------------------

def process_epic_notes(epic_notes_raw_df: pd.DataFrame) -> pd.DataFrame:
    """Filter, enrich, and clean the EPIC notes dataframe."""
    epic_notes_raw_df = epic_notes_raw_df.loc[
        epic_notes_raw_df['code_text'].isin(PROCEDURE_NAMES_OF_INTEREST_EPIC)
    ]

    # Extract and clean author type
    author_pattern = r"Author Type:\s*([^\nF]+(?:F(?!iled:)[^\nF]*)*)"
    epic_notes_raw_df['Extracted_Author_Type'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].str.extract(author_pattern)
    )
    epic_notes_raw_df['Extracted_Author_Type'] = (
        epic_notes_raw_df['Extracted_Author_Type'].str.replace(r"^\s+|\s+$", "", regex=True)
    )
    epic_notes_raw_df = epic_notes_raw_df.loc[
        epic_notes_raw_df['Extracted_Author_Type'].isin(AUTHOR_TYPES_OF_INTEREST)
    ].copy()

    # Extract header and derived fields
    epic_notes_raw_df['Header_Info'] = (
        epic_notes_raw_df["ClinicNotes.ClinicNote.summary"].apply(extract_header)
    )
    epic_notes_raw_df["Header_Date"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"by .*? at (\d{1,2}/\d{1,2}/\d{4})")
    )
    epic_notes_raw_df["Filed_Date"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"Filed: (\d{1,2}/\d{1,2}/\d{4})")
    )
    epic_notes_raw_df["Header_Date"] = pd.to_datetime(epic_notes_raw_df["Header_Date"], format="%d/%m/%Y")
    epic_notes_raw_df["Filed_Date"] = pd.to_datetime(epic_notes_raw_df["Filed_Date"], format="%d/%m/%Y")

    # Fix Header_Date when year is before 2020
    mask = epic_notes_raw_df["Header_Date"].dt.year < 2020
    epic_notes_raw_df.loc[mask, "Header_Date"] = epic_notes_raw_df.loc[mask, "Filed_Date"]

    # Extract and clean physician names
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"by (.+?) at")
    )
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Author"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
    )
    epic_notes_raw_df["Header_Author"] = (
        epic_notes_raw_df["Header_Author"].str.replace(r",?\s*MD\b.*$", "", regex=True)
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Header_Info"].str.extract(r"Cosigner:\s*([\w\s,.\-()']+)\s+at")
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Cosigner"].str.replace(r",?\s*\b[A-Z]{1,5}\b$", "", regex=True)
    )
    epic_notes_raw_df["Cosigner"] = (
        epic_notes_raw_df["Cosigner"].str.replace(r",?\s*MD\b.*$", "", regex=True)
    )

    epic_notes_raw_df['EPIC_FLAG'] = 1

    # Normalise physician name aliases
    epic_notes_raw_df['Header_Author'] = epic_notes_raw_df['Header_Author'].replace(aliasDictionary)
    epic_notes_raw_df['Cosigner'] = epic_notes_raw_df['Cosigner'].replace(aliasDictionary)

    # Clean 'bmk' lines from note text
    epic_notes_raw_df['ClinicNotes.ClinicNote.summary'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(remove_bmk_lines)
    )

    # Drop near-duplicate notes (differing only in whitespace)
    epic_notes_raw_df['remove_white_space_notes'] = (
        epic_notes_raw_df['ClinicNotes.ClinicNote.summary'].apply(lambda x: re.sub(r'\s+', '', x))
    )
    epic_notes_raw_df = epic_notes_raw_df.drop_duplicates(subset=['remove_white_space_notes'])

    # Rename and select final columns
    epic_notes_raw_df.rename(columns={
        "ClinicNotes.ClinicNote.summary": "clinical_notes",
        "Header_Date": "visit_date",
        "Header_Author": "processed_physician_name",
    }, inplace=True)

    cols_to_keep = [
        'mrn', 'PATIENT_RESEARCH_ID', 'clinical_note_id', 'code_text',
        'encounter_reference', 'clinical_notes', 'visit_date',
        'processed_physician_name', 'Cosigner', 'EPIC_FLAG',
    ]
    return epic_notes_raw_df[cols_to_keep]


# ---------------------------------------------------------------------------
# Imaging pipeline helpers
# ---------------------------------------------------------------------------

def combine_text_data_pl(
    lf: pl.LazyFrame, group_by_cols: list[str], meta_data_col: str
) -> pl.LazyFrame:
    """Concatenate split text_data rows that share the same meta_data label.

    Used for imaging reports where a single metadata field (e.g.
    'narrative_impression') can appear on multiple rows for the same visit.
    Non-matching rows are left untouched and re-combined with the result.
    """    
    lf_target = lf.filter(pl.col("meta_data") == meta_data_col)
    lf_other = lf.filter(pl.col("meta_data") != meta_data_col)

    lf_target = lf_target.with_columns(pl.col("text_data").fill_null("\n"))

    non_agg_cols = [
        c for c in lf_target.collect_schema().names()
        if c not in group_by_cols + ["text_data"]
    ]
    agg_exprs = (
        [pl.col("text_data").str.concat("").alias("text_data")]
        + [pl.col(c).first().alias(c) for c in non_agg_cols]
    )
    lf_target = lf_target.group_by(group_by_cols, maintain_order=True).agg(agg_exprs)

    return pl.concat([lf_other, lf_target])


def aggregate_imaging_columns(
    pivot_df: pd.DataFrame, notes_meta: list
) -> pd.DataFrame:
    """Merge imaging report columns into a single 'imaging_report' column."""
    cols_to_agg = [c for c in notes_meta if c in pivot_df.columns]

    pivot_df[cols_to_agg] = pivot_df[cols_to_agg].astype(str)
    pivot_df[cols_to_agg] = pivot_df[cols_to_agg].replace("nan", "")
    pivot_df[cols_to_agg] = pivot_df[cols_to_agg].replace("None", "")

    pivot_df["imaging_report"] = pivot_df[cols_to_agg].agg("\n\n".join, axis=1)
    pivot_df.drop(columns=cols_to_agg, inplace=True)
    return pivot_df


# ---------------------------------------------------------------------------
# Sub-pipeline: clinical notes
# ---------------------------------------------------------------------------

def process_clinical_notes_pipeline(
    lf: pl.LazyFrame,
    proc_name_col: str,
    visit_id_col: str,
    clinic_notes_dir: bool,
    json_dir: str,
    file_name_template: str,
    upper_limit: int,
    save_dir: str,
) -> None:
    """Polars-accelerated clinical notes pipeline.

    Polars: scan, filter, rename, MRN join, metadata column creation,
            procedure filter, clinic note adjustments, EPIC split.
    Pandas: pivot, dedup, date correction, physician processing,
            last-updated merge, EPIC integration, final save.
    """
    logger.info(f"Clinical notes pipeline — clinic_notes_dir={clinic_notes_dir}")

    # ---- EPIC split (clinic only) — stays lazy ----
    epic_lf = None
    if clinic_notes_dir:
        lf = apply_clinic_note_adjustments_pl(lf)
        if "ClinicNotes.ClinicNote.summary" in lf.collect_schema().names():
            lf, epic_lf = split_epic_epr_pl(lf)

    # ---- Filter to EPR procedures of interest ----
    lf = lf.filter(pl.col(proc_name_col).is_in(PROCEDURE_NAMES_OF_INTEREST_EPR))

    # ---- Build metadata maps ----
    map_notes_meta, map_other_meta = build_metadata_maps()
    map_meta = {**map_notes_meta, **map_other_meta}

    if clinic_notes_dir:
        # Collect EPR notes to pandas for the split_metadata_col_clinic UDF
        logger.info("Collecting EPR clinic notes to pandas for metadata splitting ...")
        df = lf.collect().to_pandas()
        df[["meta_data", "text_data"]] = pd.DataFrame(
            df["note_text"].apply(split_metadata_col_clinic).tolist(),
            index=df.index,
        )
        df = df.reset_index(drop=True)
        df = deduplicate_clinic_metadata(df)
    else:
        # Observation: create metadata columns in polars, then collect
        lf = create_metadata_pl(lf)
        logger.info("Collecting observation notes to pandas ...")
        df = lf.collect().to_pandas()

    # ---- Filter + pivot (pandas) ----
    pivot_df, df_meta = filter_and_pivot_metadata(df, map_meta)
    pivot_df = deduplicate_pivot(pivot_df, df_meta, visit_id_col)

    # ---- Post-pivot cleanup ----
    if clinic_notes_dir:
        pivot_df = fix_medical_records_report(pivot_df)

    pivot_df = aggregate_notes_columns(pivot_df, map_notes_meta, clinic_notes_dir)
    pivot_df = apply_date_corrections(pivot_df, clinic_notes_dir)
    pivot_df = process_physician(pivot_df)

    # ---- Last-updated timestamps (aggregated across all parts) ----
    logger.info("Building last_updated lookup across all file parts ...")
    df_last_updated = build_last_updated_all_parts(
        json_dir=json_dir,
        file_name_template=file_name_template,
        upper_limit=upper_limit,
        clinic_notes_dir=clinic_notes_dir,
        proc_names=PROCEDURE_NAMES_OF_INTEREST_EPR,
    )
    if not df_last_updated.empty:
        pivot_df = pivot_df.merge(
            df_last_updated,
            how="left",
            on=["PATIENT_RESEARCH_ID", visit_id_col],
        )

    # ---- Drop newline-only rows ----
    pivot_df = drop_empty_note_rows(pivot_df, note_col="clinical_notes")

    # ---- Merge EPIC notes ----
    if epic_lf is not None:
        logger.info("Processing EPIC notes ...")
        epic_df = epic_lf.collect().to_pandas()
        if not epic_df.empty:
            epic_notes_processed = process_epic_notes(epic_df)
            if not epic_notes_processed.empty:
                pivot_df = pd.concat(
                    [pivot_df, epic_notes_processed], ignore_index=True, sort=False
                )

    # ---- Final text cleanup ----
    pivot_df["clinical_notes"] = pivot_df["clinical_notes"].apply(
        lambda x: str(x).rstrip()
    )

    # ---- Save ----
    if clinic_notes_dir:
        out_path = os.path.join(save_dir, "processed_clinic_notes.parquet.gzip")
    else:
        out_path = os.path.join(save_dir, "processed_observation_notes.parquet.gzip")

    pivot_df.to_parquet(out_path, compression="gzip", index=False)
    logger.info(f"Saved: {out_path}  ({len(pivot_df):,} rows)")


# ---------------------------------------------------------------------------
# Sub-pipeline: imaging reports
# ---------------------------------------------------------------------------

def process_imaging_reports_pipeline(
    lf: pl.LazyFrame,
    visit_id_col: str,
    save_dir: str,
) -> None:
    """Polars-accelerated imaging reports pipeline."""
    logger.info("Imaging reports pipeline ...")

    # ---- Filter to imaging procedures ----
    lf = lf.filter(
        pl.col("Observations.ProcName")
        .str.to_lowercase()
        .str.strip_chars()
        .is_in(IMAGING_PROCEDURE_NAMES)
    )

    # ---- Build metadata columns ----
    lf = create_metadata_pl(lf)

    # ---- Normalize metadata labels ----
    imaging_meta_normalized = [e.replace(" ", "_") for e in IMAGING_METADATA]

    lf = (
        lf.with_columns(pl.col("meta_data").str.replace_all(" ", "_"))
        .filter(pl.col("meta_data").is_in(imaging_meta_normalized))
        .with_columns(
            pl.when(pl.col("meta_data").is_in(["narrative", "impression"]))
            .then(pl.lit("narrative_impression"))
            .when(pl.col("meta_data").is_in(["view", "area"]))
            .then(pl.lit("view_area"))
            .otherwise(pl.col("meta_data"))
            .alias("meta_data")
        )
    )

    # ---- Combine split rows for multi-line fields (polars) ----
    group_cols = ["mrn", "observation_id"]
    lf = combine_text_data_pl(lf, group_cols, "narrative_impression")
    lf = combine_text_data_pl(lf, group_cols, "view_area")

    # ---- Collect to pandas for pivot ----
    logger.info("Collecting imaging data to pandas ...")
    df = lf.collect().to_pandas()

    all_imaging_meta = [
        e for e in imaging_meta_normalized
        if e not in ["narrative", "impression", "view", "area"]
    ] + ["narrative_impression", "view_area"]
    map_meta = {e: e for e in all_imaging_meta}

    pivot_df, df_meta = filter_and_pivot_metadata(
        df, map_meta, metadata_of_interest=all_imaging_meta
    )
    pivot_df = deduplicate_pivot(pivot_df, df_meta, visit_id_col)

    # ---- Aggregate into single imaging_report column ----
    pivot_df = aggregate_imaging_columns(pivot_df, IMAGING_NOTES_METADATA)

    # ---- Drop duplicates on imaging_report ----
    pivot_df.drop_duplicates(subset=["imaging_report"], inplace=True)

    # ---- Date correction ----
    pivot_df = apply_date_corrections(pivot_df, clinic_notes_dir=False)

    # ---- Drop newline-only rows ----
    pivot_df = drop_empty_note_rows(pivot_df, note_col="imaging_report")

    # ---- Final text cleanup ----
    pivot_df["imaging_report"] = pivot_df["imaging_report"].apply(
        lambda x: str(x).rstrip()
    )

    # ---- Save ----
    out_path = os.path.join(save_dir, "processed_pe_dvt_imaging_report.parquet.gzip")
    pivot_df.to_parquet(out_path, compression="gzip", index=False)
    logger.info(f"Saved: {out_path}  ({len(pivot_df):,} rows)")


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def process_notes(
    data_dir: str,
    json_dir: str,
    save_dir: str,
    mrn_file: str,
    clinic_notes_dir: bool,
    file_glob: str,
    file_name_template: str,
    upper_limit: int,
) -> None:
    """Process all parquet parts for one note type in a single job.
      - process_clinical_notes_pipeline: consultation/clinic notes saved per
        the usual observation/clinic-notes filenames.
      - process_imaging_reports_pipeline: PE/DVT imaging reports saved
        separately (observation directory only).

    Args:
        data_dir           : directory of raw parquet files
        json_dir           : directory of raw json files (for last_updated)
        save_dir           : output directory
        mrn_file           : path to the PATIENT_RESEARCH_ID → MRN CSV
        clinic_notes_dir   : True/1 = clinic notes, False/0 = observations
        file_glob          : glob pattern matching all parquet parts,
                             e.g. "2Blast_part5_*_observations.parquet.gzip"
        file_name_template : original per-part template with 'file-part-num',
                             forwarded to get_last_updated_* helpers
        upper_limit        : highest part index (0-indexed)
    """
    os.makedirs(save_dir, exist_ok=True)

    # ---- Shared polars steps ----
    lf = scan_raw_parquet(data_dir, file_glob)
    lf = filter_valid_patient_ids_pl(lf)
    lf, proc_name_col, visit_id_col = rename_columns_pl(lf, clinic_notes_dir)
    lf = attach_mrn_pl(lf, mrn_file)

    # ---- Clinical notes pipeline ----
    process_clinical_notes_pipeline(
        lf=lf,
        proc_name_col=proc_name_col,
        visit_id_col=visit_id_col,
        clinic_notes_dir=clinic_notes_dir,
        json_dir=json_dir,
        file_name_template=file_name_template,
        upper_limit=upper_limit,
        save_dir=save_dir,
    )

    # ---- Imaging pipeline (observation only) — re-scan ----
    if not clinic_notes_dir:
        process_imaging_reports_pipeline(
            lf=lf,
            visit_id_col=visit_id_col,
            save_dir=save_dir,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process all parquet parts for one note type in a single job."
    )
    parser.add_argument("data_dir", type=str, help="Raw parquet directory")
    parser.add_argument("json_dir", type=str, help="Raw JSON directory (for last_updated)")
    parser.add_argument("save_dir", type=str, help="Output directory")
    parser.add_argument("mrn_file", type=str, help="Path to the MRN map CSV")
    parser.add_argument(
        "clinic_notes_dir",
        type=int,
        help="1 = clinic notes directory, 0 = observation directory",
    )
    parser.add_argument(
        "file_glob",
        type=str,
        help=(
            "Glob pattern for all parquet parts, "
            "e.g. '2Blast_part5_*_observations.parquet.gzip'"
        ),
    )
    parser.add_argument(
        "file_name_template",
        type=str,
        help=(
            "Per-part file name template containing 'file-part-num', "
            "e.g. '2Blast_part5_file-part-num_observations.parquet.gzip'"
        ),
    )
    parser.add_argument(
        "upper_limit",
        type=int,
        help="Highest file part number (0-indexed)",
    )
    args = parser.parse_args()

    process_notes(
        data_dir=args.data_dir,
        json_dir=args.json_dir,
        save_dir=args.save_dir,
        mrn_file=args.mrn_file,
        clinic_notes_dir=bool(args.clinic_notes_dir),
        file_glob=args.file_glob,
        file_name_template=args.file_name_template,
        upper_limit=args.upper_limit,
    )