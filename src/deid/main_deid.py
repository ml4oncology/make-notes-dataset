import argparse
import json
import os
import pandas as pd
from deid_forward_pass import deid_forward_pass
from pathlib import Path
from datetime import datetime
import numpy as np

def read_df(data_dir, df_name):
    if df_name.endswith('.csv'):
        df = pd.read_csv(f"{data_dir}/{df_name}", index_col = 0)
    elif df_name.endswith(('.parquet','.parquet.gzip')):
        df = pd.read_parquet(f"{data_dir}/{df_name}", engine='pyarrow', 
                             use_nullable_dtypes=True)
    else:
        raise Exception("dataframe format not supported")
    
    return df
def main(cfg: dict):

    data_dir = cfg['data_dir']
    df_name = cfg['df_name']
    ner_dir = cfg['ner_dir']
    pred_dir = cfg['pred_dir']
    save_dir = cfg['save_dir']
    pretrained_model_path = cfg['pretrained_model_path']
    config_file = cfg['config_file']
    eval_batch_size = cfg['eval_batch_size']

    # load data frame
    df = read_df(data_dir, df_name)

    if 'observation_id' not in df.columns:
        df['observation_id'] = range(df.shape[0])
        df['observation_id'] = df['observation_id'].astype(str)

    # adjust column names here
    if 'PATIENT_RESEARCH_ID' in df.columns:
        patient_id_col = 'PATIENT_RESEARCH_ID'
    elif 'mrn' in df.columns:
        patient_id_col = 'mrn'
    else:
        raise Exception("patient id column not found")
    df[patient_id_col] = df[patient_id_col].astype(str)

    if 'clinical_notes' in df.columns:
        note_col = 'clinical_notes'
    elif 'note' in df.columns:
        note_col = 'note'
    else:
        raise Exception("noted column not found")
    
    patient_id_list = list(df[patient_id_col].values)
    visit_id_list = list(df['observation_id'].values)
    notes_list = list(df[note_col].values)

    # write notes into jsonl file
    notes_file_name = f"notes_data_{df_name}"
    n_records = len(visit_id_list)

    if not os.path.exists(f"{data_dir}/{notes_file_name}.jsonl"):
        with open(f"{data_dir}/{notes_file_name}.jsonl", 'w') as f:
            for idx in range(n_records):
                # create dictionary
                notes_dict = {}
                notes_dict['text'] = notes_list[idx]
                notes_dict['spans'] = []
                notes_dict['meta'] = {'note_id': visit_id_list[idx],
                                       'patient_id': patient_id_list[idx]}

                f.write(json.dumps(notes_dict) + "\n")
    
    # call deid_forward_pass
    deid_forward_pass(data_dir, notes_file_name, ner_dir, 
                      pred_dir, pretrained_model_path, 
                      config_file, eval_batch_size)

    # read de-identified note
    with open(f'{data_dir}/deid_{notes_file_name}.jsonl') as f:
        deid_data = [json.loads(line) for line in f]

    patient_id_list = []
    visit_id_list = []
    deidnotes_list = []

    for record in deid_data:
        patient_id_list.append(record['meta']['patient_id'])
        visit_id_list.append(record['meta']['note_id'])
        deidnotes_list.append(record['deid_text'])

    df_deid = pd.DataFrame({patient_id_col: patient_id_list, 
                           "observation_id": visit_id_list, 
                           "deid_note": deidnotes_list})

    # add de-identified note to data frame
    if f'deid_{pretrained_model_path}' in df.columns:
        df.drop(columns=[f"deid_{pretrained_model_path}"], inplace=True)

    df = df.merge(df_deid, how='left', on=[patient_id_col,'observation_id'])
    df.drop(columns=['observation_id', note_col], inplace=True)
    df.rename(columns={f"deid_note": note_col}, inplace=True)
    
    # save updated data frame
    if df_name.endswith('.csv'):
        df.to_csv(f"{save_dir}/deid_{df_name}")
    elif df_name.endswith(('.parquet','.parquet.gzip')):
        df.to_parquet(f"{save_dir}/deid_{df_name}", compression='gzip', index=False)

    # delete the intermediate jsonl files
    os.system(f"rm {data_dir}/{notes_file_name}.jsonl")
    os.system(f"rm {data_dir}/deid_{notes_file_name}.jsonl")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", help = "directory containing the dataframe", type = str) # dataframe directory
    parser.add_argument("df_name", help = "dataframe file name", type = str) # file name of dataframe
    parser.add_argument("ner_dir", help = "ner save directory", type = str) # ner directory
    parser.add_argument("pred_dir", help = "prediction save directory", type = str) # prediction directory
    parser.add_argument("save_dir", help = "deid note save directory", type = str) # deid note save directory
    parser.add_argument("pretrained_model_path", help = "pre-trained model directory", type = str) # pretrained model directory
    parser.add_argument("config_file", help = "config file for de-id", type = str) # configuration file for de-identification
    parser.add_argument("eval_batch_size", help = "prediction batch size", type = int) # prediction for batch size
    cfg = vars(parser.parse_args())
    main(cfg)