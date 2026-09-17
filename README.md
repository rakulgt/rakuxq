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

> 当前版本：`v0.1.0-alpha.1`。视觉链路已经在多组真实截图和实体棋盘照片上跑通，但样本量
> 尚不足以宣称接近 100% 的通用准确率。RakuXQ 会明确区分自动通过与需要复核的结果。

### 为什么是 RakuXQ

- **完全本地推理**：生产识别由 OpenCV、ONNX Runtime 和本地模型完成，不调用图生文大模型。
- **面向真实世界**：包含棋盘定位、透视校正、90 个交叉点分类和局面合法性检查。
- **拒绝静默猜测**：返回 `accepted` 或 `review_required`，低可靠结果不会冒充确定答案。
- **可审计修正**：保留原始类别、置信度、自动纠正方法和规则补空坐标。
- **支持局部棋盘**：经几何计算确认在画面外的交叉点可按产品规则视为空位并显式警告。
- **快捷指令友好**：`POST /v1/fen` 直接返回纯文本 FEN，适合 iPhone 快捷指令。
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

完整、可审计的 JSON 结果：

```bash
curl -X POST http://127.0.0.1:8000/v1/recognitions \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

只返回 FEN，适合 Apple 快捷指令：

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

> Current release: `v0.1.0-alpha.1`. The vision pipeline works on a growing set of real
> screenshots and physical-board photos, but the sample size is not yet sufficient to claim
> near-perfect general accuracy. RakuXQ explicitly separates auto-accepted results from cases
> that require review.

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
- **Apple Shortcuts ready**: `POST /v1/fen` returns plain-text FEN.
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
curl -X POST http://127.0.0.1:8000/v1/recognitions \
  -F "image=@board.jpg" \
  -F "side_to_move=red"
```

Plain-text FEN for Apple Shortcuts:

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
