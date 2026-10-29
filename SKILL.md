---
name: lm-fingerprint
description: "模型指纹检测（基于 lm-detector/lmfpd）：让模型凭第一反应写出多条 1-355 的整数序列，用数字分布指纹比对参考库，识别当前对话背后真正运行的是哪个模型（GPT/Claude/Gemini/GLM/Qwen/DeepSeek/Kimi/Grok 等 64 个模型、15 个家族）。适用于：检测当前模型、我是什么模型、模型指纹、指纹检测、验货、中转站验真、API 挂羊头卖狗肉、模型识别、what model am I、model fingerprint、lm-detector、lmfpd。两种模式：自采样离线打分（无需 API key，检测自己背后的模型）和对第三方 API 端点活体检测（probe）。"
---

# lm-fingerprint — 模型指纹检测

通过让模型"凭第一反应"写出多条 1–355 的整数序列（每条约 300 个），比对各模型特有的数字分布指纹（取值偏好、区间分布、末位数字、有序块结构），在 64 个参考模型中排名，判断当前对话背后真正运行的模型。参考库覆盖 GPT、Claude、Gemini、Grok、GLM、Qwen、DeepSeek、Kimi、MiniMax、Hunyuan、Step、Seed 等 15 个家族。

**原理与局限**（务必向用户转述结论时带上）：这是**闭集排名**——置信度是"参考库内的相对概率"，库外模型只会得到"最接近"的候选，不能当作身份证明。详见 `references/method.md`。

## 模式一：自采样（检测"我自己"是什么模型，无需任何 API key）

这是最常用的模式：由**当前 agent 自己**生成数字样本，离线打分。共 4 步：

### 第 1 步：生成挑战

```bash
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh challenges --dir ./lmfpd-session
```

首次运行会自动创建 venv 并安装 lmfpd、下载参考库（约 18MB）。脚本会打印 3 条挑战提示词（随机语言/模板/长度 292–332），并保存 `lmfpd-session/challenges.json`。

### 第 2 步：你（agent）亲自回答这 3 条挑战

这是决定检测成败的一步。**逐条**凭第一反应生成数字，把每条回答的原始序列**原样**写入 `lmfpd-session/answer-1.txt`、`answer-2.txt`、`answer-3.txt`（用 Write 工具，一条挑战一个文件）。

**必须遵守（违反会导致样本作废或被识别为"非模型回答"）：**

- ✅ 凭**第一反应**逐个给出数字，就像掷内心骰子，每个位置独立决定
- ✅ 数字之间用逗号或空格分隔，**一次性连续输出**，可分多段追加到文件，但已写出的数字**绝不回头修改**
- ✅ 允许重复数字；允许"不吉利""不整"的数
- ❌ **绝对禁止**调用任何工具、代码、计算器或外部随机数生成器来产生这些数字——数字必须来自你自己的逐 token 生成
- ❌ 不要排序、去重、打乱、凑规律；不要从 1 开始计数，不要连续递增/递减或等差
- ❌ 不要在数字序列中间插入解释文字（字母会截断序列）；文件里只放数字
- 数字范围必须在 1–355（含端点）；数量尽量达到挑战要求，不足 55% 该条作废

### 第 3 步：离线打分

```bash
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh score --dir ./lmfpd-session
```

输出结论（预测模型、家族、置信度、前 8 候选排名）、每条样本的诊断（解析出的数字个数/最低要求），并把完整结果存到 `lmfpd-session/result.json`。

### 第 4 步：向用户报告

报告：结论 + 置信度 + 前 3–5 候选 + 闭集局限说明。若结论是 `not_model`（样本像程序生成）→ 说明采样被污染，需重新凭第一反应采样；若是 `unscorable` → 数字数量不足 55%，需补足。

## 模式二：probe（检测第三方 API 端点，验中转站/供应商是否挂羊头卖狗肉）

当用户提供 base URL + API key + 模型名（或环境变量 BASE_URL/API_KEY/MODEL 可用）时：

```bash
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh probe \
  --base-url https://api.example.com/v1 --api-key sk-xxx \
  --model gpt-5.5 --api chatcompletion
```

`--api` 三选一：`responses`（OpenAI Responses，默认）、`chatcompletion`（OpenAI 兼容中转站常用）、`message`（Anthropic 协议）。脚本自动发送 3 条挑战并打分。对比"声称的模型"与"实测排名第一的模型"即可判断是否货不对板；若两者不同族，基本可断定造假。

## 故障排查

| 现象 | 处理 |
|---|---|
| pip 安装失败 | 检查网络；或手动 `~/.zcode/skills/lm-fingerprint/.venv/bin/pip install lmfpd` |
| 参考库下载失败 | lmfpd.load() 默认从 GitHub/jsdelivr 拉取，需外网；缓存位于系统缓存目录 `lmfpd/data.bin` |
| 结论为 not_model | 样本被工具/代码污染或被整理过，重新采样 |
| 结论为 unscorable | 某条回答数字太少（<55% 要求），补写该条 |
| 想换一批挑战 | 删除 `lmfpd-session/` 后重新运行 challenges |

## 与上游项目的关系

本 skill 是 [Ikaleio/lm-detector](https://github.com/Ikaleio/lm-detector)（MIT 协议）的封装，调用其官方 Python SDK `lmfpd`（PyPI）完成挑战生成与打分，检测算法与参考库完全同源。参考库随上游持续更新（内置 `built_at` 标识）。
