#!/bin/bash
#PBS -l ncpus=12,ngpus=1
#PBS -l mem=90GB
#PBS -l jobfs=64GB
#PBS -q gpuvolta
#PBS -P iv96
#PBS -l walltime=24:00:00
#PBS -l storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96
#PBS -l wd

set -euo pipefail

module load singularity

IMG=/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh
INNER=/home/561/xz4320/Gadi_Hint_Guide/example/singularity_inner_script_example.sh

singularity exec \
  --nv \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root,/g/data:/g/data,/scratch:/scratch,/home:/home \
  --env PATH=/env/bin:/usr/local/bin:/usr/bin:/bin \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  --env PYTHONNOUSERSITE=1 \
  "$IMG" \
  /bin/bash "$INNER"
