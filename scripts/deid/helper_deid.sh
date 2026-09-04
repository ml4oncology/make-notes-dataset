#!/bin/bash
# Load paths from .env (gitignored; see .env.example)
_env_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.env"
if [[ ! -f "$_env_file" ]]; then
    echo "Error: $_env_file not found. Copy .env.example to .env." >&2
    exit 1
fi
set -a
source "$_env_file"
set +a

module load apptainer

container_path="$DEID_CONTAINER_PATH"
export PATH=$PATH:$(pwd)

data_dir=$1
df_name=$2
ner_dir=${data_dir}/ner
pred_dir=${data_dir}/prediction
save_dir=${data_dir}
pretrained_model_path="$DEID_MODEL_PATH"
config_file="$DEID_CONFIG_FILE"
eval_batch_size=16

apptainer exec --nv --bind $data_dir,$ner_dir,$pred_dir,$save_dir $container_path bash -c "
export MKL_THREADING_LAYER=GNU && \
export MKL_SERVICE_FORCE_INTEL=1 && \
export PYTHONPATH='' && \
conda run -n robust_deid python3 ../../src/deid/main_deid.py \
$data_dir $df_name $ner_dir $pred_dir $save_dir $pretrained_model_path $config_file $eval_batch_size"
