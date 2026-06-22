# Qixia ROCm LoRA

ROCm 单卡 LoRA 微调仓库，用 LLaMA Factory / PEFT 直接训练齐夏角色 LoRA。

这个仓库不需要额外的大模型 API key。数据是已经提取好的 ShareGPT 训练数据，直接放在仓库的 `data/` 目录里。

## Contents

- `data/qixia_train.json`: 完整训练集，6577 条 ShareGPT 样本。
- `data/qixia_valid.json`: 验证集，346 条 ShareGPT 样本。
- `data/dataset_info.json`: LLaMA Factory 数据集配置。
- `configs/qwen3_5_9b_lora.yaml`: 默认 Qwen3.5 9B LoRA 训练配置。
- `configs/qwen3_6_35b_a3b_lora.yaml`: 可选 Qwen3.6 35B-A3B LoRA 训练配置。
- `notebooks/qixia_rocm_lora_train.ipynb`: ROCm 云平台训练 notebook。
- `rocm_amd_gpu_smoke_test.ipynb`: ROCm / PyTorch 环境自检 notebook。
- `scripts/validate_dataset.py`: 训练数据格式校验。
- `scripts/patch_llamafactory_qwen35_text.py`: 让 LLaMA Factory 用 text-only 方式加载 Qwen3.5。
- `scripts/train_lora.py`: LLaMA Factory 训练入口。
- `scripts/quick_infer.py`: base model + LoRA 快速推理测试。
- `scripts/merge_lora.py`: 合并 LoRA 到 base model。

## Data

当前数据是从已清洗对白构造的 ShareGPT 格式：

```json
{
  "system": "你正在扮演《十日终焉》中的齐夏...",
  "conversations": [
    {"from": "human", "value": "上下文或用户问题"},
    {"from": "gpt", "value": "齐夏式回答"}
  ]
}
```

先用这批数据做一次 LoRA 微调。后续如果要做更强的“用户随便问”能力，可以再补一版真正聊天化数据，但这一步不需要在训练仓库里调用外部大模型 API。

## Run On ROCm Cloud

1. 打开 `rocm_amd_gpu_smoke_test.ipynb`，确认 `torch.version.hip` 有值，`torch.cuda.is_available()` 为 `True`。
2. 打开 `notebooks/qixia_rocm_lora_train.ipynb`，从上到下运行到训练前检查。
3. 运行到训练配置检查；Notebook 会用 ModelScope 把基础模型下载到持久化目录，并生成本地路径版运行时配置。
4. 把参数区的 `RUN_TRAIN = True`，运行训练单元。

默认输出：

```text
/network-workspace/outputs/qwen3_5_9b_lora
```

基础模型默认是 `Qwen/Qwen3.5-9B`。Notebook 顶部的 `MODEL_CHOICE` 默认是 `qwen3_5_9b`；如果要尝试 `Qwen/Qwen3.6-35B-A3B`，把它改成 `qwen3_6_35b_a3b`。

48GB AMD 显存建议先跑默认 9B。`Qwen/Qwen3.6-35B-A3B` 总参数更大，虽然活跃参数约 3B，但训练时仍可能需要更大显存、FP8 变体或额外 offload；这套配置先作为可选实验入口。

## Qwen3.5 Text-Only Patch

`Qwen/Qwen3.5-9B` 是原生多模态模型，但 Transformers 官方提供 `Qwen3_5ForCausalLM` 和 `Qwen3_5TextConfig` 用于纯文本生成。LLaMA Factory 默认会把它当作 `AutoModelForImageTextToText` 加载，连视觉塔一起载入；在当前 ROCm 镜像的 torch 2.9.x 下会触发 Conv3D 保护检查。

Notebook 会自动执行：

```bash
python scripts/patch_llamafactory_qwen35_text.py
```

这个脚本只改 LLaMA Factory 的加载类选择：当 `model_type == "qwen3_5"` 时使用 `Qwen3_5ForCausalLM`，并把配置切到 `config.text_config`。它是幂等的，重复运行会直接跳过。

## Current Training Parameters

默认 9B 配置：

```text
cutoff_len: 2048
per_device_train_batch_size: 2
gradient_accumulation_steps: 8
effective_batch_size: 16
lora_rank: 8
lora_alpha: 16
learning_rate: 1e-4
num_train_epochs: 1
bf16: true
gradient_checkpointing: true
disable_tqdm: false
```

这个设置比 batch size 1 更能利用 48GB 显存。训练进度条通过 `disable_tqdm: false` 开启，Notebook 的命令执行也使用实时输出。

## Local Validation

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_dataset.py data/qixia_train.json data/qixia_valid.json
```

预期数据规模：

```text
train: 6577
valid: 346
```

## Training Command

Notebook 内部会先生成运行时配置：

```text
/network-workspace/runtime_configs/qwen3_5_9b_lora.yaml
```

然后执行：

```bash
python scripts/train_lora.py --config /network-workspace/runtime_configs/qwen3_5_9b_lora.yaml
```

不要在 Hugging Face 不通的云端直接训练 `configs/*.yaml`，因为里面保留的是模型仓库 ID。Notebook 生成的运行时配置会把 `model_name_or_path` 改成本地模型目录。

## Download And Test LoRA

训练完成后，Notebook 的 `打包 LoRA 到可下载目录` 块会自动选择最新 checkpoint，并生成：

```text
/workspace/repo/downloads/qwen3_5_9b_lora_checkpoint-xxx_infer.tar.gz
```

这个文件可以从 JupyterLab 左侧文件浏览器下载到本地。它只包含推理需要的 LoRA adapter 和 tokenizer 文件，不包含 optimizer/scheduler。

Notebook 的 `交互式测试 LoRA` 块会加载 base model + 最新 LoRA，并提供：

```python
qixia_reply("如果一个规则看起来互相矛盾，你会怎么判断？")
chat_loop()
```

`chat_loop()` 可以在 Notebook 里连续输入问题，输入 `exit`、`quit` 或 `退出` 结束。

Radeon Cloud 模板里的 Notebook Path 填相对路径：

```text
notebooks/qixia_rocm_lora_train.ipynb
```
