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