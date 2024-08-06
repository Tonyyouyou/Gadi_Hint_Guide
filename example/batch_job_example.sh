#!/bin/bash
#PBS -l ncpus=64,ngpus=4
#PBS -l mem=360GB
#PBS -l jobfs=300GB
#PBS -q dgxa100 
#PBS -P ey69
#PBS -l walltime=48:00:00
#PBS -l storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96
#PBS -l wd

source /home/561/xz4320/miniconda3/etc/profile.d/conda.sh
conda activate fairseq

tar -xf /g/data/wa66/Xiangyu/Data/LibriSpeech.tar -C $PBS_JOBFS

tsv_dir="/g/data/wa66/Xiangyu/Data/fairseq_data/pretraining/layer6/tsv_folder" 
pbs_jobfs=$PBS_JOBFS

tsv_file_train="$tsv_dir/train.tsv"
tsv_file_valid="$tsv_dir/valid.tsv"

root_dir="$pbs_jobfs/LibriSpeech"

# create temp directory to save data
tsv_dir_new="$PBS_JOBFS/tsv_folder"
mkdir -p "$tsv_dir_new"


tsv_tmp_train="$tsv_dir_new/train.tsv"
tsv_tmp_valid="$tsv_dir_new/valid.tsv"


# modify the first line of tsv file
sed "1s|^.*$|$root_dir|" "$tsv_file_train" > "$tsv_tmp_train"
sed "1s|^.*$|$root_dir|" "$tsv_file_valid" > "$tsv_tmp_valid"


python3 /home/561/xz4320/fairseq/fairseq_cli/hydra_train.py \
  --config-dir /home/561/xz4320/fairseq/fairseq/examples/hubert/config/pretrain/transbimamba \
  --config-name hubert_base_transbimamba_mfcc \
  task.data=$tsv_dir_new task.label_dir=/g/data/wa66/Xiangyu/Data/fairseq_data/pretraining/transbimamba/lab_dir_mfcc task.labels='["km"]' model.label_rate=100