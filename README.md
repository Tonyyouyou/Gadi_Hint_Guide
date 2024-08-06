# Gadi_Hint_Guide
## Overview

This guide covers the basic usage methods for the Gadi supercomputer, including how to submit jobs, manage environments, run jobs with limited file numbers, and execute jobs that exceed 48 hours.

## Basic Gadi Structure
- `home`: This directory is for your environment settings and code storage. It offers **10GB** of space without any file number limitations.

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

## Enviroment

### Module Load

**Recommended:** Gadi supports the `module load` method for configuring environments. You can load Python and then use Python to create your environment. Gadi supports multiple versions of PyTorch and CUDA, all of which can be used through the `module load` method.

For example, to load Python and create an environment, you can use the following commands:

```bash
module load python/3.x.x

For more details, please refer to the [Environment Modules](https://opus.nci.org.au/display/Help/Environment+Modules) link.

### Miniconda Enviroment

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

## Managing Large Numbers of Files

Gadi has a file number limitation in the `/g/data` directory, meaning you can have large files, but not too many files. Here are three methods to address this issue:

1. **Using `tar` to Package Files:**

    You can package your files using `tar` (without compression). When you need to use the dataset, you can extract it to the `$PBS_JOBFS` temporary directory. This directory is on the node where your resources are allocated, and you can decide how much space to allocate (up to 300GB, with no file number limitations). The data in this temporary folder will be deleted after the job ends.

    Example command to untar data:
    ```bash
    tar -xf /g/data/wa66/Xiangyu/Data/LibriSpeech.tar -C $PBS_JOBFS
    ```

    For more details, refer to `batch_job_example.sh`.

2. **Using the `transformers` Package's Dataset Class:**

    The `transformers` package includes a `datasets` class that allows you to organize your data into a single file. This method can also help you manage large datasets efficiently.

    For more details, please visit the [Hugging Face Datasets documentation](https://huggingface.co/docs/datasets/en/index).

3. **Using Kaldi Supported `flac.ark` Format:**

    Another option is to use the `flac.ark` format supported by Kaldi, which can help manage large numbers of audio files efficiently.

By utilizing these methods, you can effectively manage the file number limitations on Gadi.

## Managing Jobs Exceeding 48 Hours

Gadi has a maximum job runtime limit of 48 hours. If you need to run a job for longer than this, you can refer to the `self_submit.sh` script, which contains various methods and examples. Here, I will provide the simplest method.

To automatically resubmit a job after it finishes, you can use the following command:

```bash
qsub -z -W depend=afterany:PBS_JOBID PBS_JOBNAME

In this example:
- `PBS_JOBID` is the ID of your currently running job (you can find it using `qstat`).
- `PBS_JOBNAME` is the name of the job you want to continue running or a new job.

For instance, if your job is `batch_job_example.sh` and it cannot complete within 48 hours, after submitting it with `qsub batch_job_example.sh`, you will receive a job ID (e.g., 1234). Then, you can resubmit the job using:

```bash
qsub -z -W depend=afterany:1234 batch_job_example.sh
