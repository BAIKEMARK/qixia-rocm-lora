# TaleTalk - 让小说角色活起来
一款端到端的工具，从小说文本提取角色对话，微调LoRA，一键启动聊天服务。**完全兼容之前Notebook版本的所有参数和逻辑**，不用重新学习。

## 快速开始
1. 复制配置模板
```bash
cp config.example.toml config.toml
```

2. 修改`config.toml`中的参数
   - 填小说路径、要复刻的角色名（**支持别名，逗号分隔**，第一个是规范名，比如"孙悟空,悟空,行者,孙大圣,美猴王,老孙"，别名会全部匹配）
   - 选模型、选择抽取后端（本地vLLM模型/云端API）
   - 调整训练参数（默认参数已经适配Qwen3.5 9B+48G AMD ROCm显存，直接用就行）

3. 一键跑通全流程
```bash
python main.py
```

## 和Notebook版本对应关系
所有参数和之前Notebook里的完全一致，直接把之前Notebook里改的参数抄到config.toml里就行：
| Notebook参数 | config.toml参数 | 说明 |
| --- | --- | --- |
| NOVEL_TXT | novel_txt | 小说路径 |
| TARGET_ROLE | target_role | 角色名，支持别名 |
| NOVEL_TITLE | novel_title | 小说名 |
| RUN_NAME | run_name | 运行标识 |
| MODEL_CHOICE | model_choice | 模型选择 |
| EXTRACTION_BACKEND | extraction_backend | 抽取后端 |
| MAX_WORKERS | max_workers | 并发数 |
| 训练参数（batch size、学习率等） | config.toml中对应训练字段 | 完全一致 |

## 常用命令
### 全流程自动跑
```bash
python main.py
```
自动按顺序执行：抽取对话→构建SFT数据集→训练LoRA→启动聊天服务，已完成的步骤自动跳过。

### 强制重跑某个步骤
```bash
# 重跑抽取对话和SFT构建（比如改了角色别名后不用重新训练）
python main.py -r extract build_sft
```

### 只执行某个步骤
```bash
# 只启动推理服务（训练完了直接聊天，不用重跑前面步骤）
python main.py -o infer

# 只重新构建数据集
python main.py -o build_sft
```

### 指定自定义配置文件
```bash
# 同时训练多个角色，每个角色一份配置
python main.py -c qixia_config.toml
python main.py -c wukong_config.toml
```

## 步骤说明
1. **extract（抽取对话）**：自动分块小说文本，调用LLM提取角色多轮对话，支持本地vLLM（ROCM完全兼容）或云端API（阶跃、DeepSeek等）
2. **build_sft（构建SFT数据集）**：自动合并连续对话，转成LLaMA Factory原生支持的ShareGPT格式，划分训练集/验证集
3. **train（训练LoRA）**：调用LLaMA Factory微调角色LoRA，自动适配Qwen3.5/3.6模型模板
4. **infer（启动推理服务）**：启动Gradio聊天界面，支持流式输出、多轮上下文对话，默认开启公网分享链接

## 从旧版本迁移
之前用Notebook版本跑过的原始对话数据可以直接用：
1. 把之前生成的`xxx_dialogues.jsonl`放到`data/raw/`目录下
2. 把config.toml里的`run_name`改成对应的xxx
3. 直接跑`python main.py`，会自动跳过抽取步骤，直接构建数据集训练

## 日志和输出
- 日志文件保存在`logs/`目录下，每个步骤独立带时间戳的日志文件，出错直接看对应日志回溯
- 断点续跑标记保存在`status/`目录下，已完成的步骤会自动跳过，报错重启不用从头跑
- 训练好的LoRA模型默认保存在`/network-workspace/outputs/{run_name}/`目录下，可直接导出到其他地方用
- 生成的SFT数据集保存在`data/`目录下，可直接复用给其他训练任务
- vLLM和训练的中间日志保存在`cache/`目录下

## 常见问题
### 抽取到的对话太少？
在`config.toml`里的`target_role`多补一些角色别名，比如齐夏可以写"齐夏,阿夏,夏哥,小夏"，所有别名都会被匹配。

### 训练显存不足？
调低`per_device_train_batch_size`，或者调高`gradient_accumulation_steps`保持有效batch不变；也可以把`gradient_checkpointing`改成true（会慢一些，但是省显存）。

### 推理时角色回答不对、经常OOC？
1. 增加`num_train_epochs`多训练几轮
2. 增大`lora_rank`（比如从8改成16或32）让模型拟合更好
3. 检查训练样本是不是太少，至少100条以上对话效果才会稳定

### vLLM启动失败、超时？
把`max_wait`值在src/extract.py里调大到1200，首次启动需要下载模型、编译ROCm kernel，耗时会久一些。如果还是失败，检查显存是不是被其他进程占用了。

### 如何导出LoRA给其他地方用？
训练完成后，`/network-workspace/outputs/{run_name}/`目录下的所有文件就是完整的LoRA，直接复制走就行，适配所有支持Peft的框架。
