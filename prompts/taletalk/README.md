# TaleTalk Prompt Suite

这套提示词按 `docs/superpowers/plans/2026-06-29-memory-raft-qixia.md` 设计，不受当前代码实现限制。

默认流程只需要一轮 AI：

```text
scene skeleton
-> 02_one_pass_scene_generation.md
-> scene memory + candidate samples + profile observations
```

可选 AI 提示词：

- `01_optional_dialogue_extraction.md`：没有 raw dialogue 时，从原文场景抽显式台词。
- `02_one_pass_scene_generation.md`：默认核心提示词，一轮生成记忆和候选训练样本。
- `03_enhanced_aggregate_memory.md`：增强模式第二轮，只处理重要关系/动机/跨场景事件。
- `04_risk_audit.md`：可选风险审核，只用于抽样或高风险样本。
- `05_eval_judge.md`：评测裁判，用于固定评测报告。
- `06_runtime_answer_protocol.md`：训练和运行时共享的角色回答协议。
- `07_adversarial_prompt_review.md`：对抗式审查器，用于调试上述提示词输出。
- `08_json_repair.md`：JSON/schema 修复器，用于模型输出不可解析时的最小修复重试。

每个文件中 `PROMPT_START` 到 `PROMPT_END` 之间是可直接发送给模型的 system prompt。

## 上下文长度原则

- 小场景：单次请求可放 3-5 个 scene。
- 中等场景：单次请求放 1-2 个 scene。
- 长场景或关系问题：单 scene 请求，必要时进入增强模式。
- 输入如果带 `coverage = "partial"` 或 `[TRUNCATED]`，AI 必须降低确定性，不得生成跨场景关系结论。
- 默认输出短摘要、短事件、短回答；不要把原文大段复制到输出。

## 调试

```bash
python3 scripts/prompt_lab_stepfun.py --dry-run
python3 scripts/prompt_lab_stepfun.py --cases qixia,yuniannian --repair --review
```

脚本会读取当前环境变量，或尝试读取相邻旧目录的 `.env.stepfun`。

## 约束策略

不要默认把 LangChain 作为核心依赖。推荐顺序：

1. 先用短 schema、短上下文、短输出降低失败率。
2. 再用本地 schema 校验发现不可解析或字段缺失。
3. 对失败输出调用 `08_json_repair.md` 做一次修复。
4. 生产实现可选接 Pydantic/jsonschema；LangChain 只作为适配层，不作为 TaleTalk 数据协议本身。
