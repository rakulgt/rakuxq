# RakuXQ

[![CI](https://github.com/rakulgt/rakuxq/actions/workflows/ci.yml/badge.svg)](https://github.com/rakulgt/rakuxq/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB.svg)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/rakulgt/rakuxq?include_prereleases)](https://github.com/rakulgt/rakuxq/releases)

**Robust Xiangqi image recognition today; NNUE-powered move solving tomorrow.**

**先把复杂场景中的中国象棋图片可靠转换为 FEN，再连接 NNUE 引擎计算最佳着法。**

[中文](#中文) · [English](#english)

---

## 中文

RakuXQ 是由 **rakulgt / Raku Intelligence（罗酷智能）** 发起的开源中国象棋视觉与
解题基础设施。第一阶段提供“棋盘图片 → FEN”的通用 HTTP API，面向手机截图、网页棋盘、
真实棋盘照片、斜拍、裁剪、背景噪声和部分遮挡；后续阶段将接入 NNUE 引擎，返回最佳着法、
候选变化和终端推送结果。

> 当前版本：`v0.1.1-alpha.1`。视觉链路已经在多组真实截图和实体棋盘照片上跑通，但样本量
> 尚不足以宣称接近 100% 的通用准确率。RakuXQ 会明确区分自动通过与需要复核的结果。

### 从 lgtXQ 到 RakuXQ

RakuXQ 的发起人是 **李国泰（rakulgt，<lgt@rakubank.com>）**。这个项目并非始于一次
短期的模型实验，而是来自三十余年的象棋兴趣和近二十年的象棋程序开发积累：

- **1983**：李国泰出生。
- **1988**：五岁学会中国象棋。
- **1990**：获得村级象棋比赛冠军。
- **1996**：获得中学校园象棋比赛冠军。
- **2001**：进入大学校级象棋比赛前十名。
- **2006**：开始系统学习 C++，把棋手经验转化为可执行的程序思想。
- **2008**：编写象棋推理引擎 **lgtXQ**，采用手工线性评估函数和 Alpha-Beta 搜索。
- **2018**：研发新一代象棋推理引擎 **RakuXQ**，转向 NNUE 神经网络评估函数与新一代
  Alpha-Beta 搜索体系。
- **2023**：推出局面视觉识别原型，让实体棋盘和屏幕局面能够进入计算流程。
- **2026**：将视觉能力演进为当前开源、可审计、可由 Apple 快捷指令调用的图片转 FEN
  HTTP API，并为重新接入 NNUE 解题引擎建立稳定接口。

当前公开仓库首先发布视觉识别模块；2018 年引擎的技术传承会在后续阶段以可维护、可测试的
方式重新接入，而不是把历史私有代码未经整理直接混入首版。完整项目历史见
[`docs/history.md`](docs/history.md)。

### 为什么是 RakuXQ

- **完全本地推理**：生产识别由 OpenCV、ONNX Runtime 和本地模型完成，不调用图生文大模型。
- **面向真实世界**：包含棋盘定位、透视校正、90 个交叉点分类和局面合法性检查。
- **拒绝静默猜测**：返回 `accepted` 或 `review_required`，低可靠结果不会冒充确定答案。
- **可审计修正**：保留原始类别、置信度、自动纠正方法和规则补空坐标。
- **支持局部棋盘**：经几何计算确认在画面外的交叉点可按产品规则视为空位并显式警告。
- **快捷指令友好**：推荐解析 `POST /v1/recognitions` JSON，仅在 `accepted` 时取得 `fen`。
- **可运营托管**：官方服务支持每客户独立 API Key、到期、续费和吊销。
- **为 NNUE 解题预留**：视觉层通过稳定局面契约与未来引擎层解耦。

### 处理流程

```text
JPEG / PNG / WebP
        │
        ▼
四角关键点定位 ──► 透视校正 ──► 10×9 布局分类
        │                              │
        └──── 可见性掩码 ◄────────────┘
                       │
                       ▼
         同图视觉原型复核 + 规则审计
                       │
                       ▼
          合法性检查 + 置信度门控
                       │
              ┌────────┴────────┐
              ▼                 ▼
          accepted       review_required
              │
              ▼
             FEN
```

### 快速开始

要求 Python 3.11–3.14。容器环境固定使用 Python 3.12。

```powershell
git clone https://github.com/rakulgt/rakuxq.git
cd rakuxq\apps\api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

模型权重不随源码仓库分发。请按照 [`models/README.md`](models/README.md) 获取上游模型，放置为：

```text
models/pose.onnx
models/layout.onnx
```

校验后启动：

```powershell
cd ..\..
python scripts/verify_models.py
cd apps\api
$env:RAKUXQ_POSE_MODEL = "..\..\models\pose.onnx"
$env:RAKUXQ_LAYOUT_MODEL = "..\..\models\layout.onnx"
.\.venv\Scripts\python -m uvicorn rakuxq_api.main:app --host 127.0.0.1 --port 8000
```

### HTTP API

官方托管 API：

```bash
curl -X POST https://xq.rakubank.com/v1/recognitions \
  -H "Authorization: Bearer $RAKUXQ_API_KEY" \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

客户端仅在 JSON 中 `status == "accepted"` 时读取 `fen`。官方托管服务为每位客户签发独立、
有到期日期的 Key；标准价格为 **39 元人民币/年**，到期后联系微信 **lgtqcn** 续费。
此费用对应服务器推理、带宽、密钥和运维；MIT 开源源码仍然免费。

完整、可审计的 JSON 结果：

```bash
curl -X POST http://127.0.0.1:8000/v1/recognitions \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

只返回 FEN 的本地兼容接口：

```bash
curl -X POST http://127.0.0.1:8000/v1/fen \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

实体棋盘静态图片通常不能判断轮到哪方走，因此客户端应明确传入 `red` 或 `black`。接口契约见
[`docs/api.md`](docs/api.md)，Apple 快捷指令配置见
[`docs/apple-shortcuts.md`](docs/apple-shortcuts.md)。

### 验证

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check .
.\.venv\Scripts\mypy src
```

项目关注的是**整盘零错误率**，而不只是单格准确率。正式评测将同时报告自动通过覆盖率、
自动通过结果精确率、拒识能力和延迟。

### 隐私与模型

- 图片默认只在内存中处理，不持久化，也不写入日志。
- 用户图片不会自动进入训练集。
- `.onnx` 权重、上传图片、缓存、日志和真实环境变量均被排除在 Git 之外。
- 当前基线来自 `yolo12138/Chinese_Chess_Recognition`；来源、版本和 SHA-256 记录于
  [`models/manifest.json`](models/manifest.json)。
- 本仓库发布的是 RakuXQ 源码，不重新分发第三方模型权重。

### 路线图

- [x] 图片上传、棋盘定位、透视校正与布局识别
- [x] FEN、合法性检查、置信度门控与 Apple 快捷指令接口
- [x] 局部棋盘可见性规则和同图视觉原型复核
- [ ] 授权盲测集、公开评测和自有模型训练流程
- [ ] 独立占位检测器与更多实体棋字体覆盖
- [ ] NNUE 引擎、最佳着法、候选变化和终端推送

欢迎阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 参与贡献。项目采用
[MIT License](LICENSE)。

---

## English

RakuXQ is an open-source Xiangqi vision and solving infrastructure project initiated by
**rakulgt / Raku Intelligence**. Phase one exposes a general image-to-FEN HTTP API for mobile
screenshots, web boards, physical-board photos, perspective distortion, cropping, background
noise, and partial occlusion. A later phase will add an NNUE engine for best moves, principal
variations, and terminal notifications.

> Current release: `v0.1.1-alpha.1`. The vision pipeline works on a growing set of real
> screenshots and physical-board photos, but the sample size is not yet sufficient to claim
> near-perfect general accuracy. RakuXQ explicitly separates auto-accepted results from cases
> that require review.

### From lgtXQ to RakuXQ

RakuXQ was initiated by **Li Guotai (rakulgt, <lgt@rakubank.com>)**. It is not the result of
a short-lived model experiment; it grows out of more than three decades of Xiangqi practice
and nearly two decades of chess-engine development:

- **1983** — Li Guotai was born.
- **1988** — Learned Xiangqi at the age of five.
- **1990** — Won a village Xiangqi championship.
- **1996** — Won his middle-school campus Xiangqi championship.
- **2001** — Placed in the top ten of a university Xiangqi tournament.
- **2006** — Began systematic C++ study and translating player knowledge into executable ideas.
- **2008** — Built **lgtXQ**, a Xiangqi engine based on a handcrafted linear evaluation function
  and Alpha-Beta search.
- **2018** — Developed the next-generation **RakuXQ** engine around NNUE evaluation and a newer
  Alpha-Beta search architecture.
- **2023** — Introduced a visual position-recognition prototype, connecting physical and on-screen
  boards to the computation pipeline.
- **2026** — Evolved the vision module into the current open, auditable image-to-FEN HTTP API,
  callable from Apple Shortcuts and designed for a renewed NNUE solving integration.

The public repository starts with the vision module. The 2018 engine lineage will be integrated
later through maintainable, tested interfaces instead of dropping uncurated historical private
code into the first release. See [`docs/history.md`](docs/history.md) for the full story.

### Why RakuXQ

- **Local inference**: production recognition uses OpenCV, ONNX Runtime, and local models—no
  vision-language-model API is used.
- **Built for real scenes**: board localization, perspective rectification, 90-intersection
  classification, and position validation are part of the pipeline.
- **Auditable abstention**: responses distinguish `accepted` from `review_required` instead of
  silently presenting uncertain output as fact.
- **Traceable corrections**: raw labels, confidence, correction methods, and assumed-empty
  coordinates remain available for inspection.
- **Partial-board support**: geometrically out-of-frame intersections may be treated as empty
  under an explicit, disclosed product rule.
- **Apple Shortcuts ready**: clients parse `POST /v1/recognitions` JSON and consume `fen` only
  when the status is `accepted`.
- **Operable hosting**: the hosted service supports per-customer API keys, expiration, renewal,
  and revocation.
- **NNUE-ready contract**: the future solving engine stays decoupled from the vision provider.

### Quick start

Python 3.11–3.14 is supported. The container image uses Python 3.12.

```powershell
git clone https://github.com/rakulgt/rakuxq.git
cd rakuxq\apps\api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Model weights are intentionally not committed. Follow [`models/README.md`](models/README.md),
place the files at `models/pose.onnx` and `models/layout.onnx`, verify them, and start the API:

```powershell
cd ..\..
python scripts/verify_models.py
cd apps\api
$env:RAKUXQ_POSE_MODEL = "..\..\models\pose.onnx"
$env:RAKUXQ_LAYOUT_MODEL = "..\..\models\layout.onnx"
.\.venv\Scripts\python -m uvicorn rakuxq_api.main:app --host 127.0.0.1 --port 8000
```

Detailed JSON response:

```bash
curl -X POST https://xq.rakubank.com/v1/recognitions \
  -H "Authorization: Bearer $RAKUXQ_API_KEY" \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

Clients consume `fen` only when `status == "accepted"`. Hosted keys are customer-specific and
expire independently. The standard hosted-service price is **CNY 39/year**; contact WeChat
**lgtqcn** to renew. This fee covers hosted inference, bandwidth, key management, and operations;
the MIT-licensed source remains free.

Local detailed JSON response:

```bash
curl -X POST http://127.0.0.1:8000/v1/recognitions \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

Plain-text FEN compatibility endpoint:

```bash
curl -X POST http://127.0.0.1:8000/v1/fen \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

A static physical-board image usually cannot reveal whose turn it is, so clients should provide
`red` or `black`. See [`docs/api.md`](docs/api.md) for the contract and
[`docs/apple-shortcuts.md`](docs/apple-shortcuts.md) for the iPhone workflow.

### Quality, privacy, and model provenance

RakuXQ optimizes for **exact-board accuracy**, not merely per-cell accuracy. Future public
benchmarks will report auto-accept coverage, precision of auto-accepted boards, abstention, and
latency.

Images are processed in memory by default, are not logged, and never become training data
without explicit consent. Third-party model weights are not redistributed. Their provenance,
versions, and checksums are documented in [`models/manifest.json`](models/manifest.json).

### Roadmap

- [x] Image upload, board localization, perspective rectification, and layout recognition
- [x] FEN, position validation, confidence gating, and Apple Shortcuts endpoint
- [x] Partial-board visibility rules and same-image visual prototype refinement
- [ ] Consented blind benchmark and first-party training pipeline
- [ ] Independent occupancy detector and broader physical-piece typography support
- [ ] NNUE engine, best moves, principal variations, and terminal delivery

Contributions are welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md). RakuXQ is released under
the [MIT License](LICENSE).
