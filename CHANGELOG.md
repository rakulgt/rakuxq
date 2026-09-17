# Changelog / 更新日志

All notable changes to RakuXQ are documented here.

RakuXQ 的重要版本变化记录于此。

## [0.2.0-alpha.2] - 2026-09-17

### 中文

- 首页示例改为经典残局 `3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w`。
- 棋盘改为精确矢量绘制，补齐九宫斜线、楚河汉界及炮位和兵位定位星。

### English

- Replaced the homepage example with the classic position `3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w`.
- Rebuilt the board as precise vector artwork with palace diagonals, the river, and standard cannon/pawn position marks.

## [0.2.0-alpha.1] - 2026-09-17

### 中文

- 为 `xq.rakubank.com` 增加响应式项目官网、匿名实时交互流、72 小时趋势和历史累计面板。
- 公共统计与原图审计、API Key 数据库分离；不公开客户、请求、设备或文件标识。
- 匿名累计统计库增加每日一致性备份和 30 天快照轮换。
- 增加可配置且不含 Key 的 Apple 快捷指令下载入口。
- DNS-only 正式入口强制 HTTP 跳转 HTTPS，并增加基础浏览器安全响应头。

### English

- Added a responsive project homepage with an anonymous live stream, a rolling 72-hour trend,
  and lifetime counters.
- Separated public metrics from image audits and API-key storage; no customer, request, device,
  or file identifiers are exposed.
- Added a daily consistent backup of anonymous lifetime metrics with 30-day snapshot rotation.
- Added a configurable Apple Shortcut download entry that never embeds an API key.
- Enforced HTTPS on the DNS-only production endpoint and added baseline browser security headers.

## [0.1.2-alpha.3] - 2026-09-17

### 中文

- JSON 的 `fen` 和纯文本 `/v1/fen` 改为严格返回 `piece_placement + 空格 + w/b`。
- 新增 `full_fen` 保存带 `- - 0 1` 的完整六字段形式，为后续 NNUE 引擎兼容保留。

### English

- Changed JSON `fen` and plain-text `/v1/fen` to return exactly
  `piece_placement + space + w/b`.
- Added `full_fen` for the six-field `- - 0 1` form retained for future NNUE compatibility.

## [0.1.2-alpha.2] - 2026-09-17

### 中文

- `side_to_move` 新增 `w/b`、空格加 `w/b` 与 `%20w/%20b` 输入别名，方便 Apple 快捷指令把
  同一个菜单值同时用于 API 调用和 xiangqiai.com URL 拼接。

### English

- Added `w/b`, space-prefixed `w/b`, and `%20w/%20b` aliases for `side_to_move`, allowing
  Apple Shortcuts to reuse one menu value for both API calls and xiangqiai.com URLs.

## [0.1.2-alpha.1] - 2026-09-17

### 中文

- 官方托管服务新增 12 小时短期交互审计，保存有效 Key 调用的原图、参数、完整响应、结果和耗时。
- 审计记录只保存 Key ID，不保存明文 Key；匿名和无效 Key 请求不保存请求体。
- 增加每分钟运行的自动清理、小时级访问日志轮转和 2 GiB 容量保护。

### English

- Added a 12-hour hosted interaction audit containing authenticated originals, parameters,
  complete responses, results, and timing.
- Store only the key ID in audits; never retain plaintext keys or request bodies from invalid keys.
- Added minutely expiry enforcement, hourly access-log rotation, and a 2 GiB capacity safeguard.

## [0.1.1-alpha.1] - 2026-09-17

### 中文

- 增加官方托管 API 的独立客户密钥、到期时间、吊销和续期能力。
- 密钥仅以 SHA-256 哈希保存；明文只在签发时显示一次。
- 过期响应返回结构化续费信息：微信 `lgtqcn`，`39 元人民币/年`。
- 增加 systemd、Nginx、限流、HTTPS 和原子版本目录的生产部署入口。
- 加固源站 TLS 部署：后续发布自动保留 Let's Encrypt 证书配置。
- 官方客户端默认消费 `/v1/recognitions` JSON，仅在 `status=accepted` 时读取 `fen`。

### English

- Added per-customer hosted API keys with expiration, revocation, and renewal.
- Store only SHA-256 key hashes; plaintext is shown once at issuance.
- Return structured renewal information for expired keys.
- Added production deployment assets for systemd, Nginx, rate limits, HTTPS, and atomic releases.
- Hardened origin TLS deployment so later releases preserve Let's Encrypt configuration.
- Made `/v1/recognitions` JSON the recommended client contract; clients consume `fen` only when accepted.

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
