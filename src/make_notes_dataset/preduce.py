from tqdm import tqdm
import numpy as np
import pandas as pd
from functools import partial
import logging
from collections.abc import Sequence
from typing import Optional

from common.src.util import split_and_parallelize
from common.src.constants import LAB_COLS, LAB_CHANGE_COLS, SYMP_COLS, SYMP_CHANGE_COLS

logger = logging.getLogger(__name__)

# Code by Kevin He

###############################################################################
# Engineering Features
###############################################################################
def get_change_since_prev_session(df: pd.DataFrame) -> pd.DataFrame:
    """Get change since last session"""
    cols = LAB_COLS + SYMP_COLS + ["patient_ecog"]
    change_cols = SYMP_CHANGE_COLS + LAB_CHANGE_COLS + ["patient_ecog_change"]
    result = []
    for mrn, group in tqdm(
        df.groupby("mrn"), desc="Getting change since last session..."
    ):
        change = group[cols] - group[cols].shift()
        result.append(change.reset_index().to_numpy())
    result = np.concatenate(result)

    result = pd.DataFrame(result, columns=["index"] + change_cols).set_index("index")
    result.index = result.index.astype(int)
    df = pd.concat([df, result], axis=1)

    return df

###############################################################################
# Acute Care Use
###############################################################################
def get_event_labels(
    chemo_df: pd.DataFrame, 
    event_df: pd.DataFrame, 
    event_name: str,
    lookahead_window: int = 30,
    extra_cols: Optional[list[str]] = None
) -> pd.DataFrame:
    """Extract labels for events (i.e. Emergency Department visit, hospitalization, etc) occuring within the next X days
    after visit date

    Args:
        event_df: The processed event data from https://github.com/ml4oncology/make-clinical-dataset
        lookahead_window: The lookahead window in terms of days after visit date in which labels can be extracted
        extra_cols: Additional label information to extract (e.g. triage category)
    """
    if extra_cols is None: extra_cols = []

    # extract the future event dates
    worker = partial(event_worker, event_name=event_name, lookahead_window=lookahead_window, extra_cols=extra_cols)
    result = split_and_parallelize((chemo_df, event_df), worker)
    cols = ['index', f'target_{event_name}_date'] + [f'target_{col}' for col in extra_cols]
    result = pd.DataFrame(result, columns=cols).set_index('index')
    chemo_df = chemo_df.join(result)
    
    # convert to binary label
    chemo_df[f'target_{event_name}'] = chemo_df[f'target_{event_name}_date'].notnull()

    return chemo_df


def event_worker(partition, event_name, lookahead_window: int = 30, extra_cols: Optional[list[str]] = None) -> list:
    if extra_cols is None: extra_cols = []
    
    chemo_df, event_df = partition
    result = []
    for mrn, chemo_group in tqdm(chemo_df.groupby('mrn')):
        event_group = event_df.query('mrn == @mrn')
        adm_dates = event_group['event_date']
        
        for chemo_idx, visit_date in chemo_group['treatment_date'].items():
            # get target - closest event from visit date within lookahead window
            # NOTE: if event occured on treatment date, most likely the event 
            # occured right after patient received treatment. We will deal with
            # it in downstream pipeline
            mask = adm_dates.between(visit_date, visit_date + pd.Timedelta(days=lookahead_window))
            if not mask.any():
                continue

            # assert(sum(arrival_dates == arrival_dates[mask].min()) == 1)
            tmp = event_group.loc[mask].iloc[0]
            event_date = tmp['event_date']
            extra_info = tmp[extra_cols].tolist()
            result.append([chemo_idx, event_date] + extra_info)
    return result

def get_excluded_numbers(df, mask: pd.Series, context: str = '.') -> None:
    """Report the number of patients and sessions that were excluded"""
    N_sessions = sum(~mask)
    N_patients = len(set(df['mrn']) - set(df.loc[mask, 'mrn']))
    logger.info(f'Removing {N_patients} patients and {N_sessions} sessions{context}')

def exclude_immediate_events(df: pd.DataFrame, date_cols: Sequence[str]) -> pd.DataFrame:
    """Exclude samples where any one of the target events occured immediately after"""
    mask = False
    for col in date_cols:
        days_until_event = df[col] - df['treatment_date']
        mask |= days_until_event < pd.Timedelta('2 days')
    get_excluded_numbers(df, ~mask, context=f' in which patient had a target event in less than 2 days.')
    df = df[~mask]
    return df

###############################################################################
# Symptom
###############################################################################
def convert_to_binary_symptom_labels(
    df: pd.DataFrame, scoring_map: Optional[dict[str, int]] = None
) -> pd.DataFrame:
    """Convert label to 1 (positive), 0 (negative), or -1 (missing/exclude)

    Label is positive if symptom deteriorates (score increases) by X points
    """
    if scoring_map is None:
        scoring_map = {col: 3 for col in SYMP_COLS}
    for base_col, pt in scoring_map.items():
        continuous_targ_col = f"target_{base_col}_change"
        discrete_targ_col = f"target_{base_col}_{pt}pt_change"
        missing_mask = df[continuous_targ_col].isnull()
        df[discrete_targ_col] = (df[continuous_targ_col] >= pt).astype(int)
        df.loc[missing_mask, discrete_targ_col] = -1

        # If baseline score is alrady high, we exclude them
        df.loc[df[base_col] > 10 - pt, discrete_targ_col] = -1
    return df


def get_symptom_labels(
    chemo_df: pd.DataFrame, symp_df: pd.DataFrame, lookahead_window: int = 30
) -> pd.DataFrame:
    """Extract labels for symptom deterioration within the next X days after visit date

    Args:
        symp: The processed symptom data from https://github.com/ml4oncology/make-clinical-dataset
        lookahead_window: The lookahead window in terms of days after visit date in which labels can be extracted
    """
    # extract the target symptom scores
    worker = partial(symptom_worker, lookahead_window=lookahead_window)
    result = split_and_parallelize((chemo_df, symp_df), worker)
    cols = []
    for symp in SYMP_COLS:
        cols += [f"target_{symp}_survey_date", f"target_{symp}"]
    result = pd.DataFrame(result, columns=["index"] + cols).set_index("index")
    chemo_df = pd.concat([chemo_df, result], axis=1)

    # compute target symptom score change
    for symp in SYMP_COLS:
        chemo_df[f"target_{symp}_change"] = chemo_df[f"target_{symp}"] - chemo_df[symp]

    return chemo_df


def symptom_worker(partition, lookahead_window: int = 30) -> list:
    chemo_df, symp_df = partition
    result = []
    for mrn, chemo_group in tqdm(
        chemo_df.groupby("mrn"), desc="Getting symptom labels..."
    ):
        symp_group = symp_df.query("mrn == @mrn")
        surv_dates = symp_group["survey_date"]

        for chemo_idx, visit_date in chemo_group["treatment_date"].items():
            # NOTE: the baseline ESAS score can include surveys taken on visit date.
            # To make sure the target ESAS score does not overlap with baseline ESAS score,
            # only take surveys AFTER the visit date
            mask = surv_dates.between(
                visit_date
                + pd.Timedelta(days=1),  # NOTE: you can also just do inclusive='right'
                visit_date + pd.Timedelta(days=lookahead_window),
            )
            if not mask.any():
                continue

            data = []
            for symp in SYMP_COLS:
                # take the max (worst) symptom scores within the target timeframe
                scores = symp_group.loc[mask, symp]
                idx = None if all(scores.isnull()) else scores.idxmax(skipna=True)
                data += (
                    [None, None]
                    if idx is None
                    else [surv_dates[idx], symp_group.loc[idx, symp]]
                )
            result.append([chemo_idx] + data)
    return result


def fill_missing_data(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing data that can be filled heuristically"""
    # fill the following missing data with 0
    col = "num_prior_ED_visits_within_5_years"
    df[col] = df[col].fillna(0)

    # fill the following missing data with the maximum value
    for col in ["days_since_last_treatment", "days_since_prev_ED_visit"]:
        df[col] = df[col].fillna(df[col].max())

    return df


def keep_only_one_per_week(df: pd.DataFrame) -> list[int]:
    """Keep only the first treatment session of a given week
    Drop all other sessions
    """
    keep_idxs = []
    for mrn, group in tqdm(
        df.groupby("mrn"), desc="Getting the first sessions of a given week..."
    ):
        previous_date = pd.Timestamp.min
        for i, visit_date in group["treatment_date"].items():
            if visit_date >= previous_date + pd.Timedelta(days=7):
                keep_idxs.append(i)
                previous_date = visit_date
    get_excluded_numbers(
        df, mask=df.index.isin(keep_idxs), context=f" not first of a given week"
    )
    df = df.loc[keep_idxs]
    return df


def indicate_immediate_events(
    df: pd.DataFrame, 
    targ_cols: Sequence[str], 
    date_cols: Sequence[str],
    replace_val: int = -1
) -> pd.DataFrame:
    """Indicate samples where target event occured immediately after
     
    Indicate separately for each target
    
    Args:
        replace_val: The value to replace the target to indicate the exclusion
    """
    n_events = []
    for targ_col, date_col in zip(targ_cols, date_cols):
        days_until_event = df[date_col] - df['treatment_date']
        immediate_mask = days_until_event < pd.Timedelta('2 days')
        occured_mask = df[targ_col] == 1
        print
        mask = immediate_mask & occured_mask
        df.loc[mask, targ_col] = replace_val
        n_events.append(sum(mask))
    logger.info(f'About {min(n_events)}-{max(n_events)} sessions had a target event '
                f'(e.g. {targ_cols[0]}) in less than 2 days.')
    return df