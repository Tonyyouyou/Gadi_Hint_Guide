# Gadi_Hint_Guide

## Codex Skill (Current Workflow)

The maintained, agent-facing guide is [`skills/run-on-gadi`](skills/run-on-gadi/SKILL.md). It combines current NCI guidance, a dated H200/A100/V100 queue snapshot, live allocation probes, PBS linting, file-safe environment/data tools, and reusable templates.

For this account, it is installed as:

```text
/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi
  -> ../repos/Gadi_Hint_Guide/skills/run-on-gadi
```

Invoke it in Codex as `$run-on-gadi`. The non-negotiable storage policy is:

- `/g/data/wa66/Xiangyu/.codex` is only for Codex configuration, skills, and their source repositories. Never put workload data, models, environments, caches, checkpoints, logs, or results there.
- Build expanded environments, downloads, caches, and extracted datasets only in `$PBS_JOBFS`.
- Publish environments as single `.sqsh` files in `/g/data/wa66/Xiangyu/enviroment_cache`.
- Publish packed datasets in `/g/data/wa66/Xiangyu/Data` and results in an existing/user-approved `Result*` directory.
- Re-run the live preflight for `wa66`, `ey69`, `po67`, and `iv96` before choosing a charging project; quarterly KSU and inode usage are dynamic.
- Debug through login-node `tmux` plus an explicitly approved `qsub -I`; production batch submission requires separate approval.

The older manual notes below are retained as background. Hard-coded projects, mounts, resource values, and HOME-based environment steps in those notes must not override the skill or current NCI documentation.

## Overview

This guide covers the basic usage methods for the Gadi supercomputer, including how to submit jobs, manage environments, run jobs with limited file numbers, and execute jobs that exceed 48 hours.

## Basic Gadi Structure
- `home`: This directory has a **10GB** quota. Keep only small code and shell configuration here; do not create new environments or allow caches, datasets, model downloads, checkpoints, or PBS logs to accumulate here.

- `/g/data`: This directory is for storing your data. **Warning**: There is a file number limitation for this folder, so it's recommended to tar your data to avoid issues.

- `/scratch`: This is a temporary directory, and it also has limitations. I personally don't recommend storing anything here. If this folder becomes full, it can prevent everyone in your project from using Gadi.


## Job Types

### Interactive Job

An interactive job allows you to call computing resources directly for debugging. This method is useful when you need to test and troubleshoot your code in real-time.

#### Example Interactive Jobs

There are three examples of interactive jobs, each corresponding to a different type of resource: `interactive_a100.sh`, `interactive_v100.sh`, and `interactive_cpu.sh`. These examples demonstrate how to use the A100 GPU, V100 GPU, and CPU only, respectively.

- **Interactive V100 GPU**

  To request an interactive job using a V100 GPU, use the following command:

  ```bash
  qsub -I -q gpuvolta -P wa66 -l walltime=5:00:00,ncpus=12,ngpus=1,mem=90GB,jobfs=300GB,storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96,wd
  ```

Let's take **v100 GPU** as an example:

- The `-q` option specifies the queue you are in, which can be **cpu**, **v100**, or **a100**. You can refer to the three examples I provided for specific names.
  
- For **v100**, one v100 requires **12 CPUs** (while **a100** requires **16 CPUs**).

- `mem` stands for memory. **90GB of memory per GPU** is sufficient for most tasks.

- `jobfs` is a temporary storage space on the corresponding node, with a maximum of **300GB**.

- `storage` refers to your corresponding **gdata space**, which can be stacked across multiple projects. Here, I mount storage from **four projects** simultaneously.


### Batch Job

A batch job is submitted and runs in the background. This method is ideal for running long computations that do not require real-time interaction(48 hours job most).


In the `example` folder, `batch_job_example.sh` is an example of a batch job. The basic method is similar to an interactive job. When you need to submit it, use the following command:

```bash
qsub batch_job_example.sh (your job file)
```

## Enviroment

### Module Load

**Recommended:** Gadi supports the `module load` method for configuring environments. You can load Python and then use Python to create your environment. Gadi supports multiple versions of PyTorch and CUDA, all of which can be used through the `module load` method.

For example, to load Python and create an environment, you can use the following commands:

```bash
module load python/3.x.x
```
For more details, please refer to the [Environment Modules](https://opus.nci.org.au/display/Help/Environment+Modules) link.

### Miniconda Enviroment

> Legacy background only: do not create a new expanded environment in HOME or gdata. Use the Codex skill to build it in `$PBS_JOBFS` and publish one `.sqsh` under `/g/data/wa66/Xiangyu/enviroment_cache`.

Due to the file number limitations in the `/g/data` directory on Gadi, we cannot install Miniconda there. However, since the `home` directory only has 10GB of space, some tricks are needed when installing Miniconda.

When setting up a deep learning environment, using `conda install pytorch` often exceeds the 10GB limit due to additional installations. Therefore, I recommend using `pip install` as much as possible. Based on my tests, this method helps keep the size within the 10GB limit.

Here is a basic guide to setting up a Miniconda environment:

1. **Download and install Miniconda in your `home` directory:**

    ```bash
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda
    ```

2. **Initialize Miniconda:**

    ```bash
    source $HOME/miniconda/bin/activate
    ```

3. **Create a new conda environment:**

    ```bash
    conda create -n myenv python=3.x
    ```

4. **Activate the new environment:**

    ```bash
    conda activate myenv
    ```

5. **Install necessary packages using `pip`:**

    ```bash
    pip install torch
    pip install torchvision
    pip install other_packages
    ```

By following these steps and using `pip install`, you can effectively manage the space and file number limitations on Gadi.

### Packing a Conda Environment into a Singularity SquashFS Image

If a conda environment is already working in your `home` directory, you can freeze it into one SquashFS image and store it under `/g/data`. This avoids keeping many small conda files in `/g/data`, and you can run the image directly with `singularity` without unpacking it every time.

This method is useful when:

- Your `home` directory can hold one working conda environment, but not many environments.
- You want to archive stable environments as single files.
- You want to avoid the file number limit in `/g/data`.

The recommended workflow is:

```text
develop/debug in home conda env
        -> pack inside an interactive job using $PBS_JOBFS
        -> store one .sqsh file in /g/data
        -> run/debug later with singularity shell or singularity exec
```

#### 1. Install `conda-pack`

Install `conda-pack` in your base conda environment. Using `pip` is usually safer than `conda install` here because it does not trigger large conda dependency updates.

```bash
source /home/561/xz4320/miniconda3/etc/profile.d/conda.sh
conda activate base

TMPDIR=/scratch/wa66/$USER/tmp \
python -m pip install --no-cache-dir conda-pack
```

#### 2. Start an interactive CPU job with large jobfs

Do not unpack the environment on `/g/data` or `/scratch`. Use `$PBS_JOBFS`, which is temporary local storage on the allocated node and is suitable for many temporary files.

Example:

```bash
qsub -I -qnormal -Piv96 -lwalltime=10:00:00,ncpus=36,mem=128GB,jobfs=200GB,storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96,wd
```

After the job starts, check:

```bash
echo $PBS_JOBFS
```

#### 3. Pack the environment

Below is the basic idea used by `make_env.sh`. Replace `fairseq` with your own environment name if needed.

```bash
module load singularity
source /home/561/xz4320/miniconda3/etc/profile.d/conda.sh

ENV_NAME=fairseq
TAG=$(date +%Y%m%d)
CONDA_ROOT=/home/561/xz4320/miniconda3
ENV_PREFIX=$CONDA_ROOT/envs/$ENV_NAME

OUTDIR=/g/data/wa66/Xiangyu/enviroment_cache
OUT=$OUTDIR/${ENV_NAME}-${TAG}.sqsh
BUILD=$PBS_JOBFS/conda-sqsh-build/${ENV_NAME}-${TAG}
ROOT=$BUILD/root
TAR=$BUILD/${ENV_NAME}.tar.gz

mkdir -p "$OUTDIR"
rm -rf "$BUILD"
mkdir -p "$ROOT/env"

mkdir -p "$ROOT"/{usr/bin,usr/lib,usr/lib64,usr/sbin,etc,tmp,var/tmp,home,g,scratch,jobfs,apps,opt/nci,proc,sys,dev,half-root}
chmod 1777 "$ROOT/tmp" "$ROOT/var/tmp"

ln -s usr/bin "$ROOT/bin"
ln -s usr/lib "$ROOT/lib"
ln -s usr/lib64 "$ROOT/lib64"
ln -s usr/sbin "$ROOT/sbin"

touch "$ROOT/etc/passwd" "$ROOT/etc/group" "$ROOT/etc/hosts" "$ROOT/etc/resolv.conf"

conda-pack \
  -p "$ENV_PREFIX" \
  --dest-prefix /env \
  -o "$TAR" \
  --force

tar -xzf "$TAR" -C "$ROOT/env"
rm -f "$TAR"

mksquashfs "$ROOT" "$OUT" \
  -noappend \
  -comp xz \
  -processors "${PBS_NCPUS:-2}" \
  -mem 8G \
  -no-xattrs \
  -no-progress
```

The final output is one file, for example:

```bash
/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh
```

After confirming the image works, the temporary `$PBS_JOBFS/conda-sqsh-build/...` directory can be removed. It will also disappear automatically when the job finishes.

#### 4. Test the packed image

On Gadi, some system libraries are symlinked through `/half-root`, so bind `/half-root` as well as `/usr` and `/etc`.

```bash
module load singularity

IMG=/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh

singularity exec \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  "$IMG" \
  /env/bin/python -c "import sys; print(sys.executable); print(sys.version)"
```

For a package-level test:

```bash
singularity exec \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  "$IMG" \
  /env/bin/python -c "import fairseq; print('fairseq ok')"
```

#### 5. Use the image interactively

To debug inside the environment:

```bash
module load singularity

IMG=/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh

singularity shell \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root \
  --env PATH=/env/bin:/usr/local/bin:/usr/bin:/bin \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  --env PYTHONNOUSERSITE=1 \
  "$IMG"
```

Inside the shell:

```bash
which python
python -V
python your_script.py
```

You should see:

```bash
/env/bin/python
```

#### 6. Use the image in a batch job

```bash
module load singularity

IMG=/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh

singularity exec \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  "$IMG" \
  /env/bin/python your_script.py
```

For more complex jobs, keep the PBS directives in an outer script and run a second shell script inside the container. This is useful for single-node multi-GPU or multi-node launchers such as `torchrun`, `deepspeed`, or `accelerate`.

See:

- `example/singularity_outer_pbs_example.sh`: outer PBS script that loads Singularity and enters the image.
- `example/singularity_inner_script_example.sh`: inner script that runs inside the container.

Submit the outer script only:

```bash
qsub example/singularity_outer_pbs_example.sh
```

#### 7. When to delete the original conda environment

The `.sqsh` image is read-only. It is good for running and debugging, but not for installing new packages. Before deleting the original conda environment, run a real test job and save a YAML record:

```bash
conda env export -n fairseq > /g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.yml
```

Then remove the original environment if you are confident the image works:

```bash
conda env remove -n fairseq
```

If you later need to add packages, recreate or modify the conda environment in `home`, then pack a new `.sqsh` image.

## Managing Large Numbers of Files

1. **Using `tar` to Package Files:**

    You can package your files using `tar` (without compression). When you need to use the dataset, you can extract it to the `$PBS_JOBFS` temporary directory. This directory is on the node where your resources are allocated, and you can decide how much space to allocate (up to 300GB, with no file number limitations). The data in this temporary folder will be deleted after the job ends.

    Example command to untar data:
    ```bash
    tar -xf /g/data/wa66/Xiangyu/Data/LibriSpeech.tar -C $PBS_JOBFS
    ```

    For more details, refer to `batch_job_example.sh`.

2. **Using the `transformers` Package Dataset Class:**
   The `transformers` package includes a `datasets` class that allows you to organize your data into a single file. This method can also help you manage large datasets efficiently.

    For more details, please visit the [Hugging Face Datasets documentation](https://huggingface.co/docs/datasets/en/index).
  
3. **Using Kaldi Supported `flac.ark` Format:**

    Another option is to use the `flac.ark` format supported by Kaldi, which can help manage large numbers of audio files efficiently.


## Managing Jobs Exceeding 48 Hours

Gadi has a maximum job runtime limit of 48 hours. If you need to run a job for longer than this, you can refer to the `self_submit.sh` script, which contains various methods and examples. Here, I will provide the simplest method.

To automatically resubmit a job after it finishes, you can use the following command:

```bash
qsub -z -W depend=afterany:PBS_JOBID PBS_JOBNAME
```
In this example:
- `PBS_JOBID` is the ID of your currently running job (you can find it using `qstat`).
- `PBS_JOBNAME` is the name of the job you want to continue running or a new job.

For instance, if your job is `batch_job_example.sh` and it cannot complete within 48 hours, after submitting it with `qsub batch_job_example.sh`, you will receive a job ID (e.g., 1234). Then, you can resubmit the job using:

```bash
qsub -z -W depend=afterany:1234 batch_job_example.sh
```
