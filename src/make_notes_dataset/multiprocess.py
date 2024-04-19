import itertools
import multiprocessing as mp
import numpy as np
import pandas as pd

###############################################################################
# Multiprocessing
###############################################################################
# Code by Kevin He

def parallelize(generator, worker, processes: int = 4) -> list:
    pool = mp.Pool(processes=processes)
    result = pool.map(worker, generator)
    pool.close()
    pool.join() # wait for all threads
    result = list(itertools.chain(*result))
    return result

def split_and_parallelize(data, worker, split_by_mrns: bool = True, processes: int = 4) -> list:
    """Split up the data and parallelize processing of data
    
    Args:
        data: Supports a sequence, pd.DataFrame, or tuple of pd.DataFrames 
            sharing the same patient ids
        split_by_mrns: If True, split up the data by patient ids
    """
    generator = []
    if split_by_mrns:
        mrns = data[0]['mrn'] if isinstance(data, tuple) else data['mrn']
        mrn_groupings = np.array_split(mrns.unique(), processes)
        if isinstance(data, tuple):
            for mrn_grouping in mrn_groupings:
                items = tuple(df[df['mrn'].isin(mrn_grouping)] for df in data)
                generator.append(items)
        else:
            for mrn_grouping in mrn_groupings:
                item = data[mrns.isin(mrn_grouping)]
                generator.append(item)
    else:
        # splits df into x number of partitions, where x is number of processes
        generator = np.array_split(data, processes)
    return parallelize(generator, worker, processes=processes)