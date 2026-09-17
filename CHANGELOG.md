# Changelog / 更新日志

All notable changes to RakuXQ are documented here.

RakuXQ 的重要版本变化记录于此。

## [0.1.0-alpha.1] - 2026-09-17

### 中文

- 发布图片转中国象棋 FEN 的 FastAPI HTTP 接口。
- 提供完整 JSON 结果与适合 Apple 快捷指令的纯文本 FEN 接口。
- 集成可替换的本地 ONNX 棋盘定位与 90 交叉点分类 provider。
- 支持透视校正、方向归一化、局面合法性检查、置信度门控与可审计拒识。
- 支持局部棋盘画外补空，并明确披露假设坐标。
- 增加同图视觉原型复核，纠正部分实体棋盘陌生字体错分。
- 模型权重不随源码发布；仓库仅记录来源、版本和 SHA-256。

### English

- Released a FastAPI service that converts Xiangqi board images to FEN.
- Added a detailed JSON endpoint and a plain-text FEN endpoint for Apple Shortcuts.
- Integrated replaceable local ONNX board-pose and 90-intersection layout providers.
- Added perspective correction, orientation normalization, position validation,
  confidence gating, and auditable abstention.
- Added explicit assumed-empty handling for out-of-frame cells on partial boards.
- Added conservative same-image visual prototype refinement for unfamiliar physical sets.
- Model weights are not distributed with the source; provenance, version, and SHA-256
  records are provided instead.
