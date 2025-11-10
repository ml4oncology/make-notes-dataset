import argparse
import json
from transformers import HfArgumentParser, TrainingArguments
from robust_deid.ner_datasets import DatasetCreator
from robust_deid.sequence_tagging import SequenceTagger
from robust_deid.sequence_tagging.arguments import (
    ModelArguments,
    DataTrainingArguments,
    EvaluationArguments,
)
from robust_deid.deid import TextDeid
import os

#os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:512"

def deid_forward_pass(notes_dir, notes_file_name, ner_dir, pred_dir, pretrained_dir, config_file, eval_batch_size):
    """
        De-identify clinical notes.

        notes_dir: directory where the notes to be de-identified are stored
        notes_file_name: file name of clinical note to be de-identified
        ner_dir: directory where to store the sentencized and tokenized dataset
        pred_dir: directory where to save predictions from identified PHI
        pretrained_dir: directory of the downloaded pre-trained model
        config_file: configuration file for running the model
    """

    # Initialize the path where the dataset is located (input_file).
    # Input dataset
    input_file = f'{notes_dir}/{notes_file_name}.jsonl'

    # Initialize the location where we will store the sentencized and tokenized dataset (ner_dataset_file)
    ner_dataset_file = f'{ner_dir}/sentencized_tokenized_{notes_file_name}.jsonl'
    
    # Initialize the location where we will store the model predictions (predictions_file)
    # Verify this file location - Ensure it's the same location that you will pass in the json file
    # to the sequence tagger model. i.e. output_predictions_file in the json file should have the same
    # value as below
    predictions_file = f'{pred_dir}/predictions_{notes_file_name}.jsonl'
    
    # Initialize the file that will contain the original note text and the de-identified note text
    deid_file = f'{notes_dir}/deid_{notes_file_name}.jsonl'

    # Initialize the model config. This config file contains the various parameters of the model.
    model_config = config_file

    # print('file exists?\n')
    # print( os.path.exists( ner_dataset_file ) )

    # Create the dataset creator object
    dataset_creator = DatasetCreator(
        sentencizer='en_core_sci_sm',
        tokenizer='clinical',
        max_tokens=128,
        max_prev_sentence_token=32,
        max_next_sentence_token=32,
        default_chunk_size=32,
        ignore_label='NA'
    )

    # # This function call sentencizes and tokenizes the dataset
    # # It returns a generator that iterates through the sequences.
    # # We write the output to the ner_dataset_file (in json format)

    # if ~os.path.exists( ner_dataset_file ):
    
    ner_notes = dataset_creator.create(
        input_file=input_file,
        mode='predict',
        notation='BILOU',
        token_text_key='text',
        metadata_key='meta',
        note_id_key='note_id',
        label_key='label',
        span_text_key='spans'
    )
    # Write to file
    with open(ner_dataset_file, 'w') as file:
        for ner_sentence in ner_notes:
            file.write(json.dumps(ner_sentence) + '\n')

    parser = HfArgumentParser((
        ModelArguments,
        DataTrainingArguments,
        EvaluationArguments,
        TrainingArguments
    ))
    # If we pass only one argument to the script and it's the path to a json file,
    # let's parse it to get our arguments.
    model_args, data_args, evaluation_args, training_args = parser.parse_json_file(json_file=model_config)

    # adjust model_args and data_args
    model_args.model_name_or_path = pretrained_dir
    data_args.test_file = ner_dataset_file
    data_args.output_predictions_file = predictions_file
    training_args.per_device_eval_batch_size = eval_batch_size

    # Initialize the sequence tagger
    sequence_tagger = SequenceTagger(
        task_name=data_args.task_name,
        notation=data_args.notation,
        ner_types=data_args.ner_types,
        model_name_or_path=model_args.model_name_or_path,
        config_name=model_args.config_name,
        tokenizer_name=model_args.tokenizer_name,
        post_process=model_args.post_process,
        cache_dir=model_args.cache_dir,
        model_revision=model_args.model_revision,
        use_auth_token=model_args.use_auth_token,
        threshold=model_args.threshold,
        do_lower_case=data_args.do_lower_case,
        fp16=training_args.fp16,
        seed=training_args.seed,
        local_rank=training_args.local_rank
    )

    # Load the required functions of the sequence tagger
    sequence_tagger.load()

    # Set the required data and predictions of the sequence tagger
    # Can also use data_args.test_file instead of ner_dataset_file (make sure it matches ner_dataset_file)
    sequence_tagger.set_predict(
        test_file=ner_dataset_file,
        max_test_samples=data_args.max_predict_samples,
        preprocessing_num_workers=data_args.preprocessing_num_workers,
        overwrite_cache=data_args.overwrite_cache
    )

    # Initialize the huggingface trainer
    sequence_tagger.setup_trainer(training_args=training_args)

    # Store predictions in the specified file
    predictions = sequence_tagger.predict()
    # Write predictions to a file
    with open(predictions_file, 'w') as file:
        for prediction in predictions:
            file.write(json.dumps(prediction) + '\n')

    # # Initialize the text deid object
    # text_deid = TextDeid(notation='BILOU', span_constraint='super_strict')

    # # De-identify the text - using deid_strategy=replace_informative doesn't drop the PHI from the text, but instead
    # # labels the PHI - which you can use to drop the PHI or do any other processing.
    # # If you want to drop the PHI automatically, you can use deid_strategy=remove
    # deid_notes = text_deid.run_deid(
    #     input_file=input_file,
    #     predictions_file=predictions_file,
    #     deid_strategy='replace_tag_type',
    #     keep_age=False,
    #     metadata_key='meta',
    #     note_id_key='note_id',
    #     tokens_key='tokens',
    #     predictions_key='predictions',
    #     text_key='text',
    # )

    # Initialize the text deid object
    text_deid = TextDeid(notation='BILOU', span_constraint='super_strict')

    # De-identify the text - using deid_strategy=replace_informative doesn't drop the PHI from the text, but instead
    # labels the PHI - which you can use to drop the PHI or do any other processing.
    # If you want to drop the PHI automatically, you can use deid_strategy=remove
    deid_notes = text_deid.run_deid(
        input_file=input_file,
        predictions_file=predictions_file,
        deid_strategy='replace_tag_type',
        skip_category = ["AGE","DATE"],
        keep_age=False,
        metadata_key='meta',
        note_id_key='note_id',
        tokens_key='tokens',
        predictions_key='predictions',
        text_key='text',
    )

    # replace_informative
    # Write the deidentified output to a file
    with open(deid_file, 'w') as file:
        for deid_note in deid_notes:
            file.write(json.dumps(deid_note) + '\n')

    # delete unnecessary intermediate outputs
    os.system(f"rm {ner_dataset_file}")
    os.system(f"rm {predictions_file}")

    # to do: need a script for converting notes into the jsonl format

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("notes_dir", help = "directory containing clinical note", type = str) # notes directory
    parser.add_argument("notes_file_name", help = "clinical note file name", type = str) # file name of the note to be deidentified
    parser.add_argument("ner_dir", help = "ner save directory", type = str) # ner directory
    parser.add_argument("pred_dir", help = "prediction save directory", type = str) # prediction directory
    parser.add_argument("pretrained_dir", help = "pre-trained model directory", type = str) # pretrained model directory
    parser.add_argument("config_file", help = "config file for de-id", type = str) # configuration file for de-identification
    parser.add_argument("eval_batch_size", help = "prediction batch size", type = int) # prediction for batch size
    args = parser.parse_args()

    deid_forward_pass(args.notes_dir, args.notes_file_name, args.ner_dir, args.pred_dir, args.pretrained_dir, args.config_file, args.eval_batch_size)