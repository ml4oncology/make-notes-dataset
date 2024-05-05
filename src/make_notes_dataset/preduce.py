from tqdm import tqdm
import numpy as np
import pandas as pd
from functools import partial
from sklearn.model_selection import GroupShuffleSplit
import logging
from collections.abc import Sequence
from typing import Optional

from multiprocess import split_and_parallelize

from preduceConstants import lab_cols, lab_change_cols, symp_cols, symp_change_cols

logger = logging.getLogger(__name__)

# Code by Kevin He

###############################################################################
# Engineering Features
###############################################################################
def get_change_since_prev_session(df: pd.DataFrame) -> pd.DataFrame:
    """Get change since last session"""
    cols = symp_cols + lab_cols + ['patient_ecog']
    change_cols = symp_change_cols + lab_change_cols + ['patient_ecog_change']
    result = []
    for mrn, group in tqdm(df.groupby('mrn')):
        change = group[cols] - group[cols].shift()
        result.append(change.reset_index().to_numpy())
    result = np.concatenate(result)

    result = pd.DataFrame(result, columns=['index']+change_cols).set_index('index')
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

def create_train_val_test_splits(
    data: pd.DataFrame, 
    split_date: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create the training, validation, and testing set"""
    # split data temporally based on patients first visit date
    train_data, test_data = create_temporal_cohort(data, split_date)
    # create validation set from train data (80-20 split)
    train_data, valid_data = create_random_split(train_data, test_size=0.2)

    # sanity check - make sure there are no overlap of patients in the splits
    assert(not set.intersection(set(train_data['mrn']), set(valid_data['mrn']), set(test_data['mrn'])))
    return train_data, valid_data, test_data

def create_temporal_cohort(
    df: pd.DataFrame, 
    split_date: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create the development and testing cohort by partitioning on split_date
    """
    first_date = df.groupby('mrn')['treatment_date'].min()
    first_date = df['mrn'].map(first_date)
    mask = first_date <= split_date
    dev_cohort, test_cohort = df[mask].copy(), df[~mask].copy()
    
    disp = lambda x: f"NSessions={len(x)}. NPatients={x.mrn.nunique()}"
    msg = f"Development Cohort: {disp(dev_cohort)}. Contains all patients whose first visit was on or before {split_date}"
    logger.info(msg)
    msg = f"Test Cohort: {disp(test_cohort)}. Contains all patients whose first visit was after {split_date}"
    logger.info(msg)

    return dev_cohort, test_cohort

def create_random_split(
    df: pd.DataFrame, 
    test_size: float, 
    random_state: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split data radnomly based on patient ids"""
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    patient_ids = df['mrn']
    train_idxs, test_idxs = next(gss.split(df, groups=patient_ids))
    train_data = df.iloc[train_idxs].copy()
    test_data = df.iloc[test_idxs].copy()
    return train_data, test_data

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
def convert_to_binary_symptom_labels(df: pd.DataFrame, scoring_map: Optional[dict[str, int]] = None) -> pd.DataFrame:
    """Convert label to 1 (positive), 0 (negative), or -1 (missing/exclude)

    Label is positive if symptom deteriorates (score increases) by X points
    """
    if scoring_map is None: scoring_map = {col: 3 for col in symp_cols}
    for base_col, pt in scoring_map.items():
        continuous_targ_col = f'target_{base_col}_change'
        discrete_targ_col = f'target_{base_col}_{pt}pt_change'
        missing_mask = df[continuous_targ_col].isnull()
        df[discrete_targ_col ] = (df[continuous_targ_col] >= pt).astype(int)
        df.loc[missing_mask, discrete_targ_col] = -1

        # If baseline score is alrady high, we exclude them
        df.loc[df[base_col] > 10 - pt, discrete_targ_col] = -1
    return df


def get_symptom_labels(chemo_df: pd.DataFrame, symp_df: pd.DataFrame, lookahead_window: int = 30) -> pd.DataFrame:
    """Extract labels for symptom deterioration within the next X days after visit date

    Args:
        symp: The processed symptom data from https://github.com/ml4oncology/make-clinical-dataset
        lookahead_window: The lookahead window in terms of days after visit date in which labels can be extracted
    """
    # extract the target symptom scores
    worker = partial(symptom_worker, lookahead_window=lookahead_window)
    result = split_and_parallelize((chemo_df, symp_df), worker)
    cols = []
    for symp in symp_cols:
        cols += [f'target_{symp}_survey_date', f'target_{symp}']
    result = pd.DataFrame(result, columns=['index']+cols).set_index('index')
    chemo_df = pd.concat([chemo_df, result], axis=1)
    
    # compute target symptom score change
    for symp in symp_cols: 
        chemo_df[f'target_{symp}_change'] = chemo_df[f'target_{symp}'] - chemo_df[symp]

    return chemo_df


def symptom_worker(partition, lookahead_window: int = 30) -> list:
    chemo_df, symp_df = partition
    result = []
    for mrn, chemo_group in tqdm(chemo_df.groupby('mrn'), desc='Getting symptom labels...'):
        symp_group = symp_df.query('mrn == @mrn')
        surv_dates = symp_group['survey_date']

        for chemo_idx, visit_date in chemo_group['treatment_date'].items():
            # NOTE: the baseline ESAS score can include surveys taken on visit date.
            # To make sure the target ESAS score does not overlap with baseline ESAS score,
            # only take surveys AFTER the visit date
            mask = surv_dates.between(
                visit_date + pd.Timedelta(days=1), # NOTE: you can also just do inclusive='right'
                visit_date + pd.Timedelta(days=lookahead_window)
            )
            if not mask.any():
                continue

            data = []
            for symp in symp_cols:
                # take the max (worst) symptom scores within the target timeframe
                scores = symp_group.loc[mask, symp]
                idx = None if all(scores.isnull()) else scores.idxmax(skipna=True)
                data += [None, None] if idx is None else [surv_dates[idx], symp_group.loc[idx, symp]]
            result.append([chemo_idx]+data)
    return result

def drop_samples_with_no_targets(df: pd.DataFrame, targ_cols: Sequence[str], missing_val=None) -> pd.DataFrame:
    if missing_val is None: 
        mask = df[targ_cols].isnull()
    else:
        mask = df[targ_cols] == missing_val
    mask = ~mask.all(axis=1)
    get_excluded_numbers(df, mask, context=' with no targets')
    df = df[mask]
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
        mask = immediate_mask & occured_mask
        df.loc[mask, targ_col] = replace_val
        n_events.append(sum(mask))
    logger.info(f'About {min(n_events)}-{max(n_events)} sessions had a target event '
                f'(e.g. {targ_cols[0]}) in less than 2 days.')
    return df

def get_death(df):
    df.columns = df.columns.str.lower()
    df['date_of_death'] = pd.to_datetime(df['date_of_death'], format='%d%b%Y:%H:%M:%S')
    mask = df['date_of_death'].notnull()
    df = df.loc[mask, ['medical_record_number', 'date_of_death']].drop_duplicates()
    df['medical_record_number'] = df['medical_record_number'].astype(int)
    # sort by date_of_death
    df.sort_values(by = 'date_of_death', inplace=True)
    df = df.reset_index(drop=True)
    # take the earliest date recorded if multiple records are available
    df = df.groupby('medical_record_number')['date_of_death'].first().reset_index(name='date_of_death')
    assert not any(df['medical_record_number'].duplicated())
    return df.to_numpy()