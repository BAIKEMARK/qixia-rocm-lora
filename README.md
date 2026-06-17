# Qixia ROCm LoRA

ROCm 单卡 LoRA 微调仓库，用 LLaMA Factory / PEFT 直接训练齐夏角色 LoRA。

这个仓库不需要额外的大模型 API key。数据是已经提取好的 ShareGPT 训练数据，直接放在仓库的 `data/` 目录里。

## Contents

- `data/qixia_train.json`: 完整训练集，6577 条 ShareGPT 样本。
- `data/qixia_valid.json`: 验证集，346 条 ShareGPT 样本。
- `data/dataset_info.json`: LLaMA Factory 数据集配置。
- `configs/qwen2_5_7b_lora.yaml`: 默认 LoRA 训练配置。
- `notebooks/qixia_rocm_lora_train.ipynb`: ROCm 云平台训练 notebook。
- `rocm_amd_gpu_smoke_test.ipynb`: ROCm / PyTorch 环境自检 notebook。
- `scripts/validate_dataset.py`: 训练数据格式校验。
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
3. 确认数据、显存、依赖和配置都正常。
4. 把参数区的 `RUN_TRAIN = True`，运行训练单元。

默认输出：

```text
/network-workspace/qixia-rocm-lora/outputs/qwen2_5_7b_lora
```

基础模型默认是 `Qwen/Qwen2.5-7B-Instruct`。48GB AMD 显存建议先用这个 7B 配置跑通，再考虑更大的模型或更长上下文。

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

Notebook 内部最终执行的是：

```bash
python scripts/train_lora.py --config configs/qwen2_5_7b_lora.yaml
```

也可以直接在 ROCm 环境命令行运行。
