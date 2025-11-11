#!/bin/bash

module load apptainer

container_path=/cluster/projects/gliugroup/2BLAST/containers/robust-deid-image.sif
export PATH=$PATH:$(pwd)

data_dir=$1
df_name=$2
ner_dir=${data_dir}/ner
pred_dir=${data_dir}/prediction
save_dir=${data_dir}
pretrained_model_path=/cluster/projects/gliugroup/2BLAST/LLMs/deid_roberta_i2b2
config_file=/cluster/home/t127556uhn/robust_deid-0.3.1/steps/forward_pass/run/i2b2/predict_i2b2.json
eval_batch_size=16

apptainer exec --nv --bind $data_dir,$ner_dir,$pred_dir,$save_dir $container_path bash -c "
export MKL_THREADING_LAYER=GNU && \
export MKL_SERVICE_FORCE_INTEL=1 && \
export PYTHONPATH='' && \
conda run -n robust_deid python3 ../src/main_deid.py \
$data_dir $df_name $ner_dir $pred_dir $save_dir $pretrained_model_path $config_file $eval_batch_size"
