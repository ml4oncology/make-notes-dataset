from functools import partial

from tqdm import tqdm
import pandas as pd

from common.src.util import split_and_parallelize

# Code by Kevin He

def combine_feat_to_main_data(
    main: pd.DataFrame, 
    feat: pd.DataFrame, 
    main_date_col: str, 
    feat_date_col: str, 
    **kwargs
) -> pd.DataFrame:
    """Combine feature(s) to the main dataset

    Both main and feat should have mrn and date columns
    """
    mask = main['mrn'].isin(feat['mrn'])
    worker = partial(feature_extractor, main_date_col=main_date_col, feat_date_col=feat_date_col, **kwargs)
    result = split_and_parallelize((main[mask], feat), worker)
    cols = ['index'] + feat.columns.drop(['mrn', feat_date_col]).tolist()
    result = pd.DataFrame(result, columns=cols).set_index('index')
    df = main.join(result)
    return df


def feature_extractor(
    partition, 
    main_date_col: str,
    feat_date_col: str,
    keep: str = 'last', 
    time_window: tuple[int, int] = (-5,0)
) -> list:
    """Extract either the sum, first, or last forward filled feature measurements (lab tests, symptom scores, etc) 
    taken within the time window (centered on each main visit date)

    Args:
        main_date_col: The column name of the main visit date
        feat_date_col: The column name of the feature measurement date
        time_window: The start and end of the window in terms of number of days after(+)/before(-) each visit date
        keep: Which measurements taken within the time window to keep, either `sum`, `first`, `last`
    """
    if keep not in ['first', 'last', 'sum']:
        raise ValueError('keep must be either first, last, or sum')
    
    main_df, feat_df = partition
    lower_limit, upper_limit = time_window
    keep_cols = feat_df.columns.drop(['mrn', feat_date_col])

    results = []
    for mrn, main_group in tqdm(main_df.groupby('mrn')):
        feat_group = feat_df.query('mrn == @mrn')

        for idx, date in main_group[main_date_col].items():
            earliest_date = date + pd.Timedelta(days=lower_limit)
            latest_date = date + pd.Timedelta(days=upper_limit)

            mask = feat_group[feat_date_col].between(earliest_date, latest_date)
            if not mask.any(): 
                continue

            feats = feat_group.loc[mask, keep_cols]
            if keep == 'sum':
                result = feats.sum()
            elif keep == 'first':
                result = feats.iloc[0]
            elif keep == 'last':
                result = feats.ffill().iloc[-1]

            results.append([idx]+result.tolist())
    
    return results