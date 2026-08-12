# Gadi_Hint_Guide 中文版

## Codex Skill（当前工作流）

现在维护的、供 agent 使用的指南位于 [`skills/run-on-gadi`](skills/run-on-gadi/SKILL.md)。它整合了 NCI 最新文档、带日期的 H200/A100/V100 队列快照、实时额度探测、PBS 静态检查、文件数安全的环境/数据工具和可复用模板。

这个账号上已经安装为：

```text
/g/data/wa66/Xiangyu/.codex/skills/run-on-gadi
  -> ../repos/Gadi_Hint_Guide/skills/run-on-gadi
```

在 Codex 中使用 `$run-on-gadi`。以下存储规则不可违反：

- `/g/data/wa66/Xiangyu/.codex` 只存 Codex 配置、skill 和 skill 源码仓库；禁止存放任务数据、模型、环境、缓存、checkpoint、日志和结果。
- 展开的环境、下载、缓存和解压数据只能放在 `$PBS_JOBFS`。
- 环境以单个 `.sqsh` 发布到 `/g/data/wa66/Xiangyu/enviroment_cache`。
- 打包数据存到 `/g/data/wa66/Xiangyu/Data`；结果存到已有或用户明确批准的 `Result*` 目录。
- 每次在 `wa66`、`ey69`、`po67`、`iv96` 中选择计费项目之前都重新运行实时预检；季度 KSU 和 inode 使用量是动态的。

下方旧版手工说明仅作为背景保留，其中硬编码的项目、挂载、资源数值和在 HOME 创建环境的步骤不能覆盖 skill 或 NCI 当前官方文档。

## 概览

这份指南介绍 Gadi 超算的一些基础使用方法，包括如何提交任务、管理环境、处理大量小文件，以及运行超过 48 小时的任务。

## Gadi 基础目录结构

- `home`：空间配额为 **10GB**。这里只保留少量代码和 shell 配置；不要新建环境，也不要让缓存、数据、模型下载、checkpoint 或 PBS 日志堆积在这里。

- `/g/data`：用于存放数据。**注意**：这个目录有文件数量限制，因此建议把大量小文件打包成单个文件保存。

- `/scratch`：临时目录，也有限制。我个人不建议长期在这里存放东西。如果这个目录被占满，可能会影响整个项目在 Gadi 上的使用。

## 任务类型

### 交互式任务

交互式任务可以直接申请计算资源用于调试。它适合需要实时测试和排错的场景。

#### 交互式任务示例

仓库里有三个交互式任务示例，分别对应不同资源：`interactive_a100.sh`、`interactive_v100.sh` 和 `interactive_cpu.sh`。它们分别展示如何使用 A100 GPU、V100 GPU 和纯 CPU 资源。

- **V100 GPU 交互式任务**

  申请 V100 GPU 交互式任务可以使用：

  ```bash
  qsub -I -q gpuvolta -P wa66 -l walltime=5:00:00,ncpus=12,ngpus=1,mem=90GB,jobfs=300GB,storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96,wd
  ```

以 **V100 GPU** 为例：

- `-q` 指定队列，可以是 **cpu**、**v100** 或 **a100**。具体队列名称可以参考我提供的三个示例脚本。

- 对于 **V100**，一张 V100 通常需要 **12 个 CPU**；而 **A100** 通常需要 **16 个 CPU**。

- `mem` 表示内存。对大多数任务来说，**每张 GPU 90GB 内存**通常够用。

- `jobfs` 是对应计算节点上的临时存储空间，最大可以申请到 **300GB**。

- `storage` 表示需要挂载的 **gdata 空间**，可以同时挂载多个项目。这里的例子同时挂载了四个项目的 gdata。

### 批处理任务

批处理任务提交后会在后台运行。它适合不需要实时交互的大型计算任务，尤其是接近 48 小时运行上限的任务。

`example` 文件夹里的 `batch_job_example.sh` 是一个批处理任务示例。基本写法和交互式任务类似。提交时使用：

```bash
qsub batch_job_example.sh
```

## 环境管理

### Module Load

**推荐方式：** Gadi 支持用 `module load` 配置环境。你可以加载 Python，再用 Python 创建自己的环境。Gadi 上也提供了多个版本的 PyTorch 和 CUDA，很多都可以通过 `module load` 直接使用。

例如加载 Python：

```bash
module load python/3.x.x
```

更多细节请参考 [Environment Modules](https://opus.nci.org.au/display/Help/Environment+Modules)。

### Miniconda 环境

> 仅保留为旧版背景：不要再把展开的新环境创建到 HOME 或 gdata。应通过 Codex skill 在 `$PBS_JOBFS` 中构建，再把单个 `.sqsh` 发布到 `/g/data/wa66/Xiangyu/enviroment_cache`。

由于 Gadi 的 `/g/data` 有文件数量限制，不建议把 Miniconda 安装在那里。但 `home` 目录只有 10GB，所以在 `home` 里安装 Miniconda 也需要一些技巧。

搭建深度学习环境时，如果用 `conda install pytorch`，经常会因为额外依赖太多而超过 10GB。因此我建议尽量使用 `pip install`。根据我的测试，这样更容易把环境大小控制在 10GB 内。

下面是一个基础 Miniconda 环境搭建流程：

1. **在 `home` 目录下载并安装 Miniconda：**

    ```bash
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash Miniconda3-latest-Linux-x86_64.sh -b -p $HOME/miniconda
    ```

2. **初始化 Miniconda：**

    ```bash
    source $HOME/miniconda/bin/activate
    ```

3. **创建新的 conda 环境：**

    ```bash
    conda create -n myenv python=3.x
    ```

4. **激活新环境：**

    ```bash
    conda activate myenv
    ```

5. **使用 `pip` 安装所需包：**

    ```bash
    pip install torch
    pip install torchvision
    pip install other_packages
    ```

按这个方式使用 `pip install`，可以更好地应对 Gadi 上空间和文件数限制。

### 将 Conda 环境打包成 Singularity SquashFS 镜像

如果某个 conda 环境已经在 `home` 目录里调试好了，可以把它冻结成一个 SquashFS 镜像文件，并保存到 `/g/data`。这样 `/g/data` 里只会保留一个 `.sqsh` 文件，不会产生大量 conda 小文件；之后也可以用 `singularity` 直接运行，不需要每次解包。

这个方法适合以下场景：

- `home` 目录能放下一个正在使用的 conda 环境，但放不下很多环境。
- 希望把稳定环境归档成单个文件。
- 希望避开 `/g/data` 的文件数量限制。

推荐工作流：

```text
在 home 里的 conda 环境中开发和调试
        -> 在交互式任务里使用 $PBS_JOBFS 打包
        -> 在 /g/data 中保存一个 .sqsh 文件
        -> 之后用 singularity shell 或 singularity exec 运行/调试
```

#### 1. 安装 `conda-pack`

在 base conda 环境里安装 `conda-pack`。这里通常推荐用 `pip`，因为它不会像 `conda install` 那样触发较大的 conda 依赖更新。

```bash
source /home/561/xz4320/miniconda3/etc/profile.d/conda.sh
conda activate base

TMPDIR=/scratch/wa66/$USER/tmp \
python -m pip install --no-cache-dir conda-pack
```

#### 2. 申请带大 jobfs 的 CPU 交互式任务

不要把环境解包到 `/g/data` 或 `/scratch`。应该使用 `$PBS_JOBFS`，它是当前计算节点上的临时本地存储，适合放大量临时小文件。

示例：

```bash
qsub -I -qnormal -Piv96 -lwalltime=10:00:00,ncpus=36,mem=128GB,jobfs=200GB,storage=gdata/wa66+gdata/po67+gdata/ey69+gdata/iv96,wd
```

任务启动后检查：

```bash
echo $PBS_JOBFS
```

#### 3. 打包环境

下面是 `make_env.sh` 使用的核心思路。如果要打包别的环境，把 `fairseq` 替换成你的环境名即可。

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

最终输出是一个单文件，例如：

```bash
/g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.sqsh
```

确认镜像可用后，可以删除 `$PBS_JOBFS/conda-sqsh-build/...` 里的临时目录。任务结束时，`$PBS_JOBFS` 里的内容也会自动消失。

#### 4. 测试打包好的镜像

在 Gadi 上，有些系统库会通过 `/half-root` 这个路径做符号链接，所以除了 `/usr` 和 `/etc`，也需要把 `/half-root` bind 进去。

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

测试具体包是否可用：

```bash
singularity exec \
  --cleanenv \
  --bind /usr:/usr,/etc:/etc,/half-root:/half-root \
  --env LD_LIBRARY_PATH=/env/lib:/lib64:/usr/lib64 \
  "$IMG" \
  /env/bin/python -c "import fairseq; print('fairseq ok')"
```

#### 5. 交互式使用镜像

进入环境调试：

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

进入 shell 后：

```bash
which python
python -V
python your_script.py
```

你应该看到：

```bash
/env/bin/python
```

#### 6. 在批处理任务里使用镜像

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

对于更复杂的任务，可以把 PBS 指令放在外层脚本里，然后在容器里运行第二个 shell 脚本。这种写法适合单机多卡或多机多卡任务，例如 `torchrun`、`deepspeed` 或 `accelerate`。

可以参考：

- `example/singularity_outer_pbs_example.sh`：外层 PBS 脚本，负责加载 Singularity 并进入镜像。
- `example/singularity_inner_script_example.sh`：内层脚本，在容器内部运行真正的训练或推理逻辑。

提交时只提交外层脚本：

```bash
qsub example/singularity_outer_pbs_example.sh
```

#### 7. 什么时候可以删除原始 conda 环境

`.sqsh` 镜像是只读的。它适合运行和调试，但不适合继续安装新包。删除原始 conda 环境前，建议先跑一个真实任务，并保存一份 YAML 记录：

```bash
conda env export -n fairseq > /g/data/wa66/Xiangyu/enviroment_cache/fairseq-20260514.yml
```

确认镜像没问题后，可以删除原始环境：

```bash
conda env remove -n fairseq
```

如果以后还需要加包，可以在 `home` 里重新创建或修改 conda 环境，再打包一个新的 `.sqsh` 镜像。

## 管理大量文件

1. **使用 `tar` 打包文件：**

    可以用 `tar` 打包文件，不需要压缩。当需要使用数据集时，可以把它解包到 `$PBS_JOBFS` 临时目录。这个目录位于你申请到的计算节点上，空间大小由你申请的 `jobfs` 决定，最大可到 300GB，并且没有文件数限制。任务结束后，这个临时目录里的数据会被删除。

    解包示例：

    ```bash
    tar -xf /g/data/wa66/Xiangyu/Data/LibriSpeech.tar -C $PBS_JOBFS
    ```

    更多细节可以参考 `batch_job_example.sh`。

2. **使用 `transformers` 包的数据集类：**

    `transformers` 包包含 `datasets` 类，可以把数据组织成单个文件。这种方式也能帮助高效管理大型数据集。

    更多信息请参考 [Hugging Face Datasets documentation](https://huggingface.co/docs/datasets/en/index)。

3. **使用 Kaldi 支持的 `flac.ark` 格式：**

    另一个选择是使用 Kaldi 支持的 `flac.ark` 格式，它可以高效管理大量音频文件。

## 管理超过 48 小时的任务

Gadi 的单个任务最长运行时间限制为 48 小时。如果任务需要运行更久，可以参考 `self_submit.sh` 脚本，里面包含多种方法和示例。这里介绍最简单的一种。

任务结束后自动重新提交，可以使用：

```bash
qsub -z -W depend=afterany:PBS_JOBID PBS_JOBNAME
```

其中：

- `PBS_JOBID` 是当前运行任务的 ID，可以通过 `qstat` 查看。
- `PBS_JOBNAME` 是你希望继续运行或重新提交的任务脚本名称。

例如，如果任务脚本是 `batch_job_example.sh`，并且无法在 48 小时内完成，那么用 `qsub batch_job_example.sh` 提交后会得到一个任务 ID，例如 `1234`。之后可以这样续交：

```bash
qsub -z -W depend=afterany:1234 batch_job_example.sh
```
