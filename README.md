# lm-fingerprint-skill

**模型指纹检测 Skill** —— 让任何 AI agent（ZCode / Claude Code / Codex / 任意支持 skills 或能跑脚本的 agent）一键检测自己背后真正运行的是哪个大模型。

基于开源项目 [Ikaleio/lm-detector](https://github.com/Ikaleio/lm-detector)（MIT 协议）的官方 Python SDK [`lmfpd`](https://pypi.org/project/lmfpd/) 封装，检测算法与参考库完全同源：参考库覆盖 **64 个模型 / 15 个家族**（GPT、Claude、Gemini、Grok、GLM、Qwen、DeepSeek、Kimi、MiniMax、Hunyuan、Step、Seed、MiMo、Muse 等），并随上游持续更新。

## 它能干什么

- **自检模式**：agent 自己凭第一反应写出几组 1–355 的整数，离线打分识别"我是什么模型"。**不需要任何 API key**。
- **验货模式（probe）**：给第三方 API 端点（中转站/供应商）发标准挑战，实测其背后模型，与声称的模型对比，识别"挂羊头卖狗肉"。

## 实测效果

两次独立采样，均正确识别出被测 agent 的真实模型（GLM-5.3）：

```
==============================================================
模型指纹检测结果 (lm-detector / lmfpd)
==============================================================
结论: glm-5.3  (id: glm-5.3)
家族: GLM
置信度: 99.8%（参考库内闭集概率）
模式: 完整排名（库内校准置信度）

候选排名（前 8）:
  1. glm-5.3                      score=   3.297  p=99.8%  [GLM]
  2. claude-opus-5                score=   1.722  p= 0.1%  [Claude]
  3. claude-opus-4.8              score=   1.703  p= 0.0%  [Claude]
  ...

样本诊断:
  样本 1: 解析出 331 个数字 (最低要求 183) -> 有效
  样本 2: 解析出 332 个数字 (最低要求 183) -> 有效
  样本 3: 解析出 306 个数字 (最低要求 169) -> 有效
  序列形态: lag-1 自相关 -0.479, 小步占比 0.000, 像模型回答
```

另一轮独立采样（不同语言、不同长度的挑战）得出 glm-5.3 / 置信度 92.5%，两轮一致。

## 原理（一分钟版）

LLM 写不出真随机数：被要求"凭第一反应写约 300 个 1–355 的整数"时，每个模型对特定数字、数值区间、末位数字、序列起伏方式都有**稳定且私有**的偏好（源自分词器差异、训练语料沉淀、采样特性）。

检测管线：

1. **采样**：3 条挑战（语言从中/英/日/韩/法随机、模板随机组合、长度 292–332 随机），与上游建库使用同一生成器，分布一致；
2. **特征**：Hellinger 平滑频次分布 + 有序块特征（4 段区间直方图 + 末位数字分布）+ 位置特征；
3. **排名**：LDA 线性判别 + kNN 参考距离（按各模型自身离散度归一）+ 干扰基消除（扣除提示语言/模板造成的偏移）三路融合；
4. **置信度**：ranking-temperature 校准，输出**库内闭集概率**；
5. **防作弊**：序列形态检验（lag-1 自相关 / 小步占比）——用代码生成、排序或打乱过的数字会被直接判为"非模型回答"拒绝打分。

详细说明见 [`references/method.md`](references/method.md)。

## 安装

### ZCode（本仓库的主要目标）

```bash
git clone https://github.com/dake2482/lm-fingerprint-skill.git ~/.zcode/skills/lm-fingerprint
```

克隆后即为 skill 目录（含 `SKILL.md`）。首次运行自动创建 venv、安装 `lmfpd`、下载参考库（约 18MB，之后走缓存）。

### 其他 agent 框架

把本仓库放进对应框架的 skills/commands 目录即可；没有 skill 机制的 agent 也可以直接跑脚本（见下文"手动使用"），或把 [`SKILL.md`](SKILL.md) 的流程作为提示词喂给它。

依赖：`python3 ≥ 3.10` + 网络（首次安装依赖与下载参考库）。

## 使用

### 模式一：自检（检测"我自己"是什么模型）

在对话中对 agent 说"**检测一下我背后是什么模型**"（或"模型指纹"、“验下货”），skill 会引导 agent 执行四步；等价的手动流程：

```bash
# 1. 生成 3 条挑战（打印提示词，保存 challenges.json）
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh challenges --dir ./lmfpd-session

# 2. agent 亲自逐条凭第一反应回答挑战，把原始数字序列分别写入
#    lmfpd-session/answer-1.txt / answer-2.txt / answer-3.txt
#    （禁止用任何工具/代码生成数字！禁止排序/去重！允许重复！）

# 3. 离线打分
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh score --dir ./lmfpd-session
```

采样的纪律是成败关键，SKILL.md 中已写死给 agent 的规则：凭第一反应逐个给数字、不调用工具、不排序去重、不回头修改、一次性连续输出。

### 模式二：验货（检测第三方 API 端点）

```bash
bash ~/.zcode/skills/lm-fingerprint/scripts/run.sh probe \
  --base-url https://api.example.com/v1 \
  --api-key sk-xxx \
  --model gpt-5.5 \
  --api chatcompletion
```

`--api` 三选一：`responses`（OpenAI Responses，默认）/ `chatcompletion`（OpenAI 兼容中转站）/ `message`（Anthropic 协议）。实测排名第一的模型与声称的模型**不同家族**，即可基本断定货不对板。

## 参考库如何保持新鲜

不靠定时器，靠**惰性刷新**（stale-while-revalidate）：每次运行若距上次检查 ≥ 24 小时，后台线程静默拉取新版参考库（先比对几 KB 的 manifest，有更新才下载主体），下次运行生效。数据源为官方站 `lm.ikale.io`，失败自动回落 jsDelivr 国内镜像。强制立即更新：

```bash
rm ~/Library/Caches/lmfpd/data.bin   # macOS；Linux 为 ~/.cache/lmfpd/data.bin
```

## 常见问题

| 现象 | 说明 / 处理 |
|---|---|
| 结论是 `not_model` | 样本被工具/代码污染或被整理过（排序/去重），重新凭第一反应采样 |
| 结论是 `unscorable` | 某条回答数字数量不足要求的 55%，补写该条 |
| 置信度高但模型不对？ | 置信度是**库内 64 个模型的闭集概率**，库外模型只会得到"最接近"的候选；看前几名是否聚集同一家族更稳 |
| pip 安装失败 | 检查网络；或手动 `~/.zcode/skills/lm-fingerprint/.venv/bin/pip install lmfpd` |
| 想换一批挑战 | 删除会话目录后重新运行 `challenges` |

## 仓库结构

```
├── SKILL.md                 # skill 主文件（agent 读取的操作规程）
├── README.md
├── scripts/
│   ├── run.sh               # 引导脚本：自动 venv + 安装 lmfpd
│   └── lmfpd_tool.py        # challenges / score / probe 三合一工具
└── references/
    └── method.md            # 检测原理与局限（agent 解释结论时引用）
```

## 许可与致谢

- 本 skill 以 [MIT](LICENSE) 协议开源。
- 检测能力完全来自上游 [Ikaleio/lm-detector](https://github.com/Ikaleio/lm-detector)（MIT），其算法思路与部分数据源自 [xqy2006/ModelTrace](https://github.com/xqy2006/ModelTrace)。
- 结果是**统计指纹证据**，不构成身份证明；请勿用于违反他人服务条款的场景。
