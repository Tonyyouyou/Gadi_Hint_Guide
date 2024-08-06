# Gadi_Hint_Guide
## Overview

This guide covers the basic usage methods for the Gadi supercomputer, including how to submit jobs, manage environments, run jobs with limited file numbers, and execute jobs that exceed 48 hours.

## Basic Gadi Structure
home is the directory for your enviroment setting, code stroage

/g/data is the directory for store your data. Warning: Tar your data, there is file number limitations for this folder

/scratch is the temp directory, there is also limitation for this folder, I personally dont suggest to store anything in this folder. Because once this folder is full, noboday can use gadi in your project

## Job Types

### Interactive Job

An interactive job allows you to call computing resources directly for debugging. This method is useful when you need to test and troubleshoot your code in real-time.

#### Example Interactive Jobs

There are three examples of interactive jobs, each corresponding to a different type of resource: `interactive_a100`, `interactive_v100`, and `interactive_cpu`. These examples demonstrate how to use the A100 GPU, V100 GPU, and CPU only, respectively.

- **Interactive V100 GPU**

  To request an interactive job using a V100 GPU, use the following command:

  ```bash
  qsub -I -q gpuvolta -P wa66 -l walltime=5:00:00,ncpus=12,ngpus=1,mem=90GB,jobfs=300GB,storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96,wd

In the example, there are three cases: interactive_a100, interactive_v100, and interactive_cpu, which correspond to using a100 GPU, v100 GPU, and CPU only, respectively.
Let's take v100 GPU as an example. The `-q` option is the queue you are in, which can be cpu, v100, or a100. You can refer to the three examples I provided for specific names. For v100, one v100 requires 12 CPUs (16 for a100). `mem` is memory; 90GB of memory per GPU is sufficient for most tasks. `jobfs` is a temporary storage space on the corresponding node, with a maximum of 300GB. `storage` is your corresponding gdata space, which can be stacked across multiple projects. Here, I mount storage from four projects simultaneously.



### Batch Job

A batch job is submitted and runs in the background. This method is ideal for running long computations that do not require real-time interaction.