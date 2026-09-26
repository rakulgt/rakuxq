# RakuXQ

[![CI](https://github.com/rakulgt/rakuxq/actions/workflows/ci.yml/badge.svg)](https://github.com/rakulgt/rakuxq/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11--3.14-3776AB.svg)](https://www.python.org/)
[![Release](https://img.shields.io/github/v/release/rakulgt/rakuxq?include_prereleases)](https://github.com/rakulgt/rakuxq/releases)

**Robust Xiangqi image recognition with a clean path to NNUE-powered move analysis.**

**先把复杂场景中的中国象棋图片可靠转换为 FEN，再连接 NNUE 引擎计算最佳着法。**

[中文](#中文) · [English](#english)

---

## 中文

RakuXQ 是由 **rakulgt / Raku Intelligence（罗酷智能）** 发起的开源中国象棋视觉与
解题基础设施。第一阶段提供“棋盘图片 → FEN”的通用 HTTP API，面向手机截图、网页棋盘、
真实棋盘照片、斜拍、裁剪、背景噪声和部分遮挡；`v0.3` 已增加可替换 UCI 引擎边界，开始
返回最佳着法和候选变化，后续继续完成中文着法与终端推送。

> 当前源码版本：`v0.4.4-alpha.3`。视觉链路已经在多组真实截图和实体棋盘照片上跑通；
> Pikafish UCI 适配器进入本地非商业技术验证。官方托管服务暂不部署受限 NNUE 权重。

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

当前公开仓库先以视觉识别模块建立可靠输入，`v0.3` 再以可维护、可测试的独立适配层接入
解题引擎，而不是把历史私有代码未经整理直接混入首版。完整项目历史见
[`docs/history.md`](docs/history.md)。

### 为什么是 RakuXQ

- **完全本地推理**：生产识别由 OpenCV、ONNX Runtime 和本地模型完成，不调用图生文大模型。
- **面向真实世界**：包含棋盘定位、透视校正、90 个交叉点分类和局面合法性检查。
- **拒绝静默猜测**：返回 `accepted` 或 `review_required`，低可靠结果不会冒充确定答案。
- **可审计修正**：保留原始类别、置信度、自动纠正方法和规则补空坐标。
- **可诊断延迟**：托管 API 返回标准 `Server-Timing`，短期审计将鉴权、图片接收、应用处理、响应发送与总耗时分段记录。
- **支持局部棋盘**：经几何计算确认在画面外的交叉点可按产品规则视为空位并显式警告。
- **快捷指令友好**：推荐解析 `POST /v1/recognitions` JSON，仅在 `accepted` 时取得 `fen`。
- **可运营托管**：官方服务支持每客户独立 API Key、到期、续费和吊销。
- **视觉与解题解耦**：引擎只消费稳定 FEN 契约，可替换而不影响识别 provider。
- **双路径接口**：`/v1/analyses` 分析已有 FEN，`/v1/solve` 仅对自动通过的图片局面给出着法。
- **公开运行面板**：官网匿名展示最近 72 小时交互与历史累计统计，不公开原图或客户标识。
- **即领即试**：公开开发文档可领取明文只显示一次、6 分钟失效的临时测试 Key。
- **交互局面研究器**：首页经典残局支持合法落点、走子、吃子、悔棋、重置、实时 FEN 与外部深入研究。
- **RakuXQ Lab**：标准 FEN 直达统一研究工作台；桌面顶栏、分组侧边菜单和常驻招法轨提供一键标准新局、引擎执红/黑、分析与立即出招、分支导航、翻转、自由摆子、本地文件导入、保存分享和非破坏变化树。

### 标准 FEN 直达

把两字段或六字段中国象棋 FEN 直接接在固定前缀后即可打开实验室；浏览器会把空格编码为 `%20`：

```text
https://xq.rakubank.com/fen/3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4%20w
```

竞品风格的 `/#/<FEN>` 和通用 `/lab?fen=<FEN>` 也会被兼容解析。API Key 永远不进入 URL。

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

公开开发教程与临时测试 Key：<https://xq.rakubank.com/developers>

```bash
curl -X POST https://xq.rakubank.com/v1/recognitions \
  -H "Authorization: Bearer $RAKUXQ_API_KEY" \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

客户端仅在 JSON 中 `status == "accepted"` 时读取 `fen`。官方托管服务为每位客户签发独立、
有到期日期的 Key；标准价格为 **39 元人民币/年**，到期后联系微信 **lgtqcn** 续费。
此费用对应服务器推理、带宽、密钥和运维；MIT 开源源码仍然免费。

`fen` 字段严格返回 `piece_placement + 一个真实空格 + w/b`；需要带 `- - 0 1` 的完整
六字段形式时读取 `full_fen`。

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

### 本地引擎分析（实验性）

`v0.3` 可以通过 UCI 控制用户另行安装的 Pikafish，返回 ICCS 最佳着法、PV、搜索信息以及
固定红方视角的整数评分。普通局面显示 `+186`、`-243` 或 `0`；杀棋显示 `KO(+N)` 或
`KO(-N)`。Pikafish 程序和官方 NNUE 权重均不随本仓库分发，当前路线仅用于本地非商业
互操作验证；生产商用前必须取得权重授权。安装、环境变量和调用示例见
[`docs/engine.md`](docs/engine.md)。

### 验证

```powershell
cd apps\api
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check .
.\.venv\Scripts\mypy src
cd ..\..
npm ci
npm run vendor:xiangqi
npm run test:web
```

项目关注的是**整盘零错误率**，而不只是单格准确率。正式评测将同时报告自动通过覆盖率、
自动通过结果精确率、拒识能力和延迟。

### 隐私与模型

- 自托管默认只在内存中处理图片。官方托管服务为早期质量分析保存已鉴权调用的原图、请求和响应，最长 12 小时后自动删除。
- 短期审计图片不会自动进入长期样本集或训练集；API Key 明文永不写入审计日志。
- 官网公开记录只包含时间、状态、简化 FEN、置信度与耗时，72 小时后删除；累计层只保留汇总数字。
- `.onnx` 权重、上传图片、缓存、日志和真实环境变量均被排除在 Git 之外。
- 当前基线来自 `yolo12138/Chinese_Chess_Recognition`；来源、版本和 SHA-256 记录于
  [`models/manifest.json`](models/manifest.json)。
- 本仓库发布的是 RakuXQ 源码，不重新分发第三方模型权重。
- 首页规则层固定使用 BSD-2-Clause `xiangqi.js`；版本、用途和完整许可见
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。棋盘视觉和交互由 RakuXQ 自己实现。

### 路线图

- [x] 图片上传、棋盘定位、透视校正与布局识别
- [x] FEN、合法性检查、置信度门控与 Apple 快捷指令接口
- [x] 局部棋盘可见性规则和同图视觉原型复核
- [x] 匿名实时官网、72 小时交互流与历史累计统计
- [x] FEN 驱动的首页交互局面研究器与合法走子规则
- [ ] 授权盲测集、公开评测和自有模型训练流程
- [ ] 独立占位检测器与更多实体棋字体覆盖
- [x] 可替换 UCI 引擎边界、Pikafish 本地适配、最佳着法与主要变化 API
- [x] 标准 FEN 直达的 RakuXQ Lab、标准新局、自由摆子、变化树、双方独立 AI 辅导与本地棋谱导入导出
- [ ] 可主动创建的永久棋谱分享链接与自动化引擎竞技场
- [ ] 获得可用于托管服务的 NNUE 权重授权或训练 RakuXQ 自有权重
- [ ] 中文着法转换、候选多变化和终端推送

欢迎阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 参与贡献。项目采用
[MIT License](LICENSE)。

---

## English

RakuXQ is an open-source Xiangqi vision and solving infrastructure project initiated by
**rakulgt / Raku Intelligence**. Phase one exposes a general image-to-FEN HTTP API for mobile
screenshots, web boards, physical-board photos, perspective distortion, cropping, background
noise, and partial occlusion. Version `0.3` adds a replaceable UCI engine boundary for best moves
and principal variations; Chinese notation and terminal notifications remain on the roadmap.

> Current source release: `v0.4.4-alpha.3`. The vision pipeline works on a growing set of real
> screenshots and physical-board photos. The Pikafish UCI adapter is undergoing local,
> non-commercial interoperability validation; restricted NNUE weights are not deployed by the
> official hosted service.

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
- **Diagnosable latency**: the hosted API emits standard `Server-Timing` metrics and splits
  short-lived audit timing into authentication, request receipt, application work, response send,
  and total time.
- **Partial-board support**: geometrically out-of-frame intersections may be treated as empty
  under an explicit, disclosed product rule.
- **Apple Shortcuts ready**: clients parse `POST /v1/recognitions` JSON and consume `fen` only
  when the status is `accepted`.
- **Operable hosting**: the hosted service supports per-customer API keys, expiration, renewal,
  and revocation.
- **Decoupled solving**: engines consume a stable FEN contract and remain replaceable without
  changing the vision provider.
- **Two analysis paths**: `/v1/analyses` consumes confirmed FEN, while `/v1/solve` analyzes only
  auto-accepted image recognition results.
- **Public operating pulse**: the homepage shows anonymous 72-hour activity and lifetime totals
  without exposing images or customer identifiers.
- **Instant trial access**: the public developer guide can issue a one-time-display test key that
  expires after six minutes.
- **Interactive position playground**: the homepage puzzle supports legal targets, moves,
  captures, undo, reset, live FEN, and handoff to an external analysis page.
- **RakuXQ Lab**: a standard-FEN deep link opens one compact workspace with a desktop action bar,
  grouped side drawer, persistent move rail, one-click standard new game, per-side engine control,
  analysis/play-now actions, branch navigation, position editing, import/export, and local recovery.

### Standard FEN deep links

Append a two-field or six-field Xiangqi FEN to the fixed prefix; browsers encode the separating
space as `%20`:

```text
https://xq.rakubank.com/fen/3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4%20w
```

Competitor-style `/#/<FEN>` and generic `/lab?fen=<FEN>` inputs are accepted as compatibility
aliases. API keys never belong in a URL.

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

The `fen` field is exactly `piece_placement + one literal space + w/b`; clients that need the
six-field `- - 0 1` form should read `full_fen`.

`side_to_move` accepts `red/black`, `w/b`, and the URL-ready `%20w/%20b` aliases. The latter lets
Apple Shortcuts reuse one menu value when calling the API and building a xiangqiai.com viewer URL.

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

### Local engine analysis (experimental)

RakuXQ `v0.3` can control a separately installed Pikafish process through UCI and return an ICCS
best move, PV, search metadata, and an integer score with a fixed red perspective. Ordinary scores
are displayed as `+186`, `-243`, or `0`; forced mates use `KO(+N)` or `KO(-N)`. Neither Pikafish nor
its official NNUE weights are distributed by this repository. The current path is limited to local,
non-commercial interoperability validation until hosted-use authorization is obtained. See
[`docs/engine.md`](docs/engine.md) for setup, environment variables, licensing boundaries, and API
examples.

### Quality, privacy, and model provenance

RakuXQ optimizes for **exact-board accuracy**, not merely per-cell accuracy. Future public
benchmarks will report auto-accept coverage, precision of auto-accepted boards, abstention, and
latency.

Self-hosted deployments process images in memory by default. The official hosted service keeps
authenticated originals, requests, and responses for at most 12 hours for early quality analysis.
Short-lived audits never become a permanent dataset or training data automatically, and plaintext
API keys are never logged. Third-party model weights are not redistributed. Their provenance,
versions, and checksums are documented in [`models/manifest.json`](models/manifest.json).
Public event rows contain only time, status, simplified FEN, confidence, and latency, and disappear
after 72 hours; only aggregate lifetime counters persist.

### Roadmap

- [x] Image upload, board localization, perspective rectification, and layout recognition
- [x] FEN, position validation, confidence gating, and Apple Shortcuts endpoint
- [x] Partial-board visibility rules and same-image visual prototype refinement
- [x] Anonymous live homepage, rolling 72-hour activity, and lifetime counters
- [ ] Consented blind benchmark and first-party training pipeline
- [ ] Independent occupancy detector and broader physical-piece typography support
- [x] Replaceable UCI boundary, local Pikafish adapter, best-move and principal-variation APIs
- [x] Standard-FEN RakuXQ Lab, true new game, position editor, variation tree, independent
  assistance for both sides, and local game import/export
- [ ] Explicit permanent game-share links and an automated engine arena
- [ ] Obtain hosted-use NNUE authorization or train a first-party RakuXQ network
- [ ] Chinese move notation, multiple candidate lines, and terminal delivery

Contributions are welcome; see [`CONTRIBUTING.md`](CONTRIBUTING.md). RakuXQ is released under
the [MIT License](LICENSE).
