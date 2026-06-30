# TaleTalk 记忆 / RAFT 中文使用说明

本文说明当前 `codex/memory-raft-qixia` 分支里的 memory-first / RAFT 数据流程怎么用。

## 先说结论

旧数据能不能复用，要分清是哪一种旧数据：

- 可以复用：`data/raw/*_dialogues.jsonl`
- 不建议直接复用：旧的 `data/*_chat_train.json` / `data/*_chat_valid.json`
- 需要重新生成：`profile`、`scene memory`、`BM25 index`、`RAFT train/valid`

原因很简单：RAFT 数据不是“旧问答数据换个名字”。它的每条训练样本都要带角色设定和记忆片段，让模型学习：

```text
事实从记忆来
口吻从角色来
资料不足时不要编
```

旧的 SFT 数据只有普通多轮对话，没有 `【记忆片段】`，所以不能直接当 RAFT 数据用。

## 当前流程

新的流程是：

```text
extract
-> build_memory
-> build_sft
-> train
-> infer
```

其中：

- `extract`：从小说抽原始对话，输出 `data/raw/{run_name}_dialogues.jsonl`
- `build_memory`：从 raw dialogue 生成角色 profile、scene memory、BM25 index
- `build_sft`：生成普通 style 数据、RAFT 数据，或 mixed 混合数据
- `train`：后续云端训练 LoRA，本地可以不跑
- `infer`：推理时可加载 memory index，按用户问题检索记忆片段

## 齐夏现成用法

齐夏配置在：

```bash
configs/shiri_qixia.toml
```

它已经启用：

```toml
enable_memory = true
memory_backend = "bm25"
sft_mode = "mixed"
style_data_ratio = 0.35
raft_data_ratio = 0.65
```

如果本地已有原始抽取结果：

```bash
data/raw/shiri_qixia_dialogues.jsonl
```

就不需要重新调用 StepFun，也不需要重新抽取，直接跑：

```bash
python3 main.py -c configs/shiri_qixia.toml -r build_memory build_sft -o build_memory build_sft
```

这条命令只会生成记忆和训练数据，不会训练。

## 云端服务器怎么拉这个分支

在云端 `/workspace/repo` 里：

```bash
cd /workspace/repo
git fetch origin codex/memory-raft-qixia
git switch codex/memory-raft-qixia
```

如果云端工作区有本地改过的 notebook 或数据文件导致切分支失败，先确认这些改动不要保留，再处理。不要直接覆盖没看过的文件。

## 输出文件

跑完 `build_memory build_sft` 后，主要输出：

```text
data/profiles/shiri_qixia_profile.json
data/memory/shiri_qixia_scenes.jsonl
data/memory/shiri_qixia_bm25.json
data/shiri_qixia_chat_train.json
data/shiri_qixia_chat_valid.json
data/shiri_qixia_raft_train.json
data/shiri_qixia_raft_valid.json
```

含义：

- `profile.json`：角色设定卡。可以人工编辑，建议后面认真改。
- `scenes.jsonl`：场景记忆库。现在 v1 是从 chunk/dialogue 启发式构建。
- `bm25.json`：本地检索索引。推理时用它找相关记忆。
- `*_raft_train.json`：纯 RAFT 数据，所有样本都带记忆片段。
- `*_chat_train.json`：当前配置下是 mixed 数据，包含 style 样本和 RAFT 样本，训练默认用这个。

## 怎么验证

本地不训练时，至少跑这些：

```bash
python3 -m pytest -q
python3 scripts/validate_dataset.py data/shiri_qixia_chat_train.json
python3 scripts/validate_dataset.py data/shiri_qixia_raft_train.json
```

预期：

- pytest 全部通过
- dataset validator 输出 examples / turns / chars 统计
- 不启动 ROCm 训练

## 如果没有 raw dialogue

如果没有：

```text
data/raw/shiri_qixia_dialogues.jsonl
```

才需要重新抽取。

本地可以用 StepFun：

1. 先把配置里的抽取后端改成云端 API：

```toml
extraction_backend = "cloud_api"
```

2. 再加载仓库根目录 `.env` 并执行：

```bash
set -a
source .env
set +a

python3 main.py -c configs/shiri_qixia.toml -r extract build_memory build_sft -o extract build_memory build_sft
```

注意：

- `.env` 不提交到 Git；旧的 `.env.stepfun` 只作为兼容文件，不再推荐新建。
- 这条命令会花 API 钱。
- 如果已有 raw dialogue，不要重复跑 extract。
- 如果 `extraction_backend` 还是 `local_model`，程序会尝试启动本地 vLLM，而不是 StepFun。

## 训练时用哪个数据

当前 `train` 步骤默认读取：

```text
data/{run_name}_chat_train.json
data/{run_name}_chat_valid.json
```

在 `sft_mode = "mixed"` 时，这两个文件已经是 mixed 数据。

所以云端训练时仍然可以跑：

```bash
python3 main.py -c configs/shiri_qixia.toml -o train
```

或全流程：

```bash
python3 main.py -c configs/shiri_qixia.toml
```

但如果你已经本地生成并上传了数据，云端不需要重新 extract。

## 推理时怎么用 memory

`infer` 会尝试读取：

```text
data/profiles/{run_name}_profile.json
data/memory/{run_name}_bm25.json
```

如果存在，推理时会：

```text
用户问题
-> BM25 检索相关 scene memory
-> 拼进角色 system prompt
-> LoRA 生成回答
```

如果不存在，就退回旧的纯 LoRA system prompt。

## 现在这版的边界

当前是 v1，可跑通，但不是最终版：

- `target_role_knows` 目前是启发式：角色出现在 chunk 里就认为知道。
- memory scene 还不是精细章节/事件级切分。
- RAFT distractor 和 no-answer 样本字段已预留，但 v1 还没有真正生成复杂干扰样本。
- profile 是默认生成的，后续应该人工编辑或用 LLM 总结增强。

这版的目标是先把正确的数据管线跑通：旧 raw dialogue -> memory -> RAFT/mixed SFT -> 推理可检索记忆。
