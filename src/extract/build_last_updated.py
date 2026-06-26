import pandas as pd
import logging
import json
import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from make_notes_dataset.notes_pipeline.constants import PROCEDURE_NAMES_OF_INTEREST_EPR

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_last_updated_obs_notes(jsonDir, filePartNum, filename, procNames):
    """
        Extract the lastUpdated column from the raw json file since it's not present
        in the processed CSV files.

        jsonDir: directory where the raw json files are saved
        filePartNum: file part number to be processed
        filename: file name of the json file
        procNames: list of procedure names of interest
    """
    # load the json file
    filename = filename.replace('file-part-num', str(filePartNum)).replace('parquet.gzip', 'json')
    jsonFileName = f'{jsonDir}/{filename}'

    with open(jsonFileName) as json_file:
        data = json.load(json_file)

    # tabulate patient id, obs id, last updated
    
    # procedure names of interest
    procNames = [x.lower() for x in procNames]

    patientList = []
    obsIDList = []
    lastUpdatedList = []

    for idx in range(len(data)):
        nObs = len(data[idx]['Observations'])
        for jdx in range(nObs):
            if str(data[idx]['Observations'][jdx]['ProcName']).lower() in procNames:
                patientList.append(data[idx]['PATIENT_RESEARCH_ID'])
                obsIDList.append(data[idx]['Observations'][jdx]['Observation']['_id'])
                lastUpdatedList.append(data[idx]['Observations'][jdx]['Observation']['meta']['lastUpdated'])

    dfLastUpdated = pd.DataFrame({'PATIENT_RESEARCH_ID': patientList, 'observation_id': obsIDList, 'last_updated': lastUpdatedList})

    return dfLastUpdated

def get_last_updated_clinic_ci_notes(jsonDir, filePartNum, filename, procNames):
    """
        Extract the lastUpdated column from the raw json file since it's not present
        in the processed CSV files. This is only for the clinic .CI notes.

        jsonDir: directory where the raw json files are saved
        filePartNum: file part number to be processed
        filename: file name of the json file
        procNames: list of procedure names of interest
    """
    # load the json file
    filename = filename.replace('file-part-num', str(filePartNum)).replace('parquet.gzip', 'json')
    jsonFileName = f'{jsonDir}/{filename}'

    with open(jsonFileName) as json_file:
        data = json.load(json_file)

    # tabulate patient id, obs id, last updated

    patientList = []
    clinicIDList = []
    lastUpdatedList = []

    for idx in range(len(data)):
        nObs = len(data[idx]['ClinicNotes'])
        for jdx in range(nObs):
            if str(data[idx]['ClinicNotes'][jdx]['ClinicNote']['code']['text']) in procNames:
                patientList.append(data[idx]['PATIENT_RESEARCH_ID'])
                clinicIDList.append(data[idx]['ClinicNotes'][jdx]['ClinicNote']['_id'])
                lastUpdatedList.append(data[idx]['ClinicNotes'][jdx]['ClinicNote']['meta']['lastUpdated'])

    dfLastUpdated = pd.DataFrame({'PATIENT_RESEARCH_ID': patientList, 'clinical_note_id': clinicIDList, 'last_updated': lastUpdatedList})

    return dfLastUpdated

def _fetch_last_updated_part(args):
    """Top-level worker function (must be picklable — no lambdas)."""
    json_dir, i, file_name_template, clinic_notes_dir, proc_names = args
    try:
        if clinic_notes_dir:
            df_part = get_last_updated_clinic_ci_notes(
                json_dir, i, file_name_template, proc_names
            )
        else:
            df_part = get_last_updated_obs_notes(
                json_dir, i, file_name_template, proc_names
            )
        return df_part if (df_part is not None and not df_part.empty) else None
    except Exception as exc:
        logger.warning(f"get_last_updated failed for part {i}: {exc}")
        return None


def build_last_updated_all_parts(
    json_dir: str,
    file_name_template: str,
    upper_limit: int,
    clinic_notes_dir: bool,
    save_dir: str,
    n_workers: int | None = None,
) -> pd.DataFrame:
    """Collect last-updated timestamps for every file part in parallel.

    Args:
        n_workers: number of worker processes. Defaults to os.cpu_count(),
                   which on a dedicated HPC node gives you all available cores.
                   Cap it (e.g. n_workers=32) if your sysadmin has limits.
    """
    proc_names = PROCEDURE_NAMES_OF_INTEREST_EPR
    args_list = [
        (json_dir, i, file_name_template, clinic_notes_dir, proc_names)
        for i in range(upper_limit + 1)
    ]

    frames = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_fetch_last_updated_part, args): args[1]
                   for args in args_list}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                frames.append(result)

    if not frames:
        logger.warning("No last_updated data found — returning empty DataFrame.")
        return pd.DataFrame()

    df_last_updated = pd.concat(frames, ignore_index=True)
    dir_type = "clinic" if clinic_notes_dir else "observation"
    df_last_updated.to_csv(f"{save_dir}/last_updated_{dir_type}.csv", index=False)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get last updated dates from json files."
    )
    parser.add_argument("json_dir", type=str, help="Raw JSON directory (for last_updated)")
    parser.add_argument("save_dir", type=str, help="Output directory")
    parser.add_argument(
        "clinic_notes_dir",
        type=int,
        help="1 = clinic notes directory, 0 = observation directory",
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
    parser.add_argument(
        "n_workers",
        type=int,
        help="Number of worker processes to use. Defaults to os.cpu_count().",
    )
    args = parser.parse_args()

    build_last_updated_all_parts(
        json_dir=args.json_dir,
        file_name_template=args.file_name_template,
        upper_limit=args.upper_limit,
        clinic_notes_dir=bool(args.clinic_notes_dir),
        save_dir=args.save_dir,
        n_workers=args.n_workers
    )