# Changelog / 更新日志

All notable changes to RakuXQ are documented here.

RakuXQ 的重要版本变化记录于此。

## [0.3.0-alpha.1] - 2026-09-18

### 中文

- 增加独立、可替换的 UCI 引擎边界和 Pikafish 常驻进程适配器，不与视觉 provider 耦合。
- 新增 `/v1/analyses`（FEN → 最佳着法）和 `/v1/solve`（图片 → FEN → 最佳着法）。
- 评分统一为红方固定视角整数；普通评分显示 `+N/-N/0`，杀棋显示 `KO(+N)/KO(-N)`。
- 返回 ICCS 最佳着法、ponder、PV、深度、节点、耗时、引擎版本和 NNUE 权重 SHA-256。
- 严格校验 FEN，限制搜索时间，并在超时/崩溃后终止故障进程，避免 Pikafish 严格校验退出影响视觉服务。
- Pikafish 与官方 NNUE 权重不随 MIT 仓库或生产服务分发；当前仅完成本地非商业技术验证。

### English

- Added a separate, replaceable UCI engine boundary and persistent Pikafish process adapter,
  decoupled from the vision provider.
- Added `/v1/analyses` (FEN to best move) and `/v1/solve` (image to FEN to best move).
- Standardized integer scores on a fixed red perspective, with `+N/-N/0` and `KO(+N)/KO(-N)`.
- Return ICCS best move, ponder, PV, depth, nodes, elapsed time, engine version, and NNUE SHA-256.
- Validate FEN strictly, cap search time, and terminate failed processes without taking down vision.
- Pikafish and official NNUE weights are not distributed or deployed; validation is local and
  non-commercial at this stage.

## [0.2.1-alpha.1] - 2026-09-18

### 中文

- 将首页静态棋盘升级为 RakuXQ 原生交互局面研究器，支持合法落点提示、走子、吃子、悔棋、重置和实时 FEN。
- 当前局面可以直接复制，或携带 `%20w/%20b` 跳转到 xiangqiai.com 深入研究。
- 规则层采用固定提交的 BSD-2-Clause `xiangqi.js`，棋盘 UI、移动端交互和视觉仍由 RakuXQ 自己实现；依赖来源和许可已纳入仓库。
- 增加浏览器规则测试、依赖再生成一致性检查和独立 Web CI。

### English

- Upgraded the static homepage board into a native RakuXQ position playground with legal targets, moves, captures, undo, reset, and live FEN.
- The current position can be copied or opened on xiangqiai.com with the encoded `%20w/%20b` separator.
- Pinned the BSD-2-Clause `xiangqi.js` rules layer while keeping rendering, mobile interaction, and visual design native to RakuXQ; provenance and licensing are bundled.
- Added browser-rule tests, deterministic vendor checks, and a dedicated web CI job.

## [0.2.0-alpha.4] - 2026-09-18

### 中文

- 移除首页示例棋盘卡片的装饰性旋转，使卡片、棋盘和页面网格保持水平端正。
- 更新静态资源版本参数，避免浏览器继续使用旧版倾斜样式。

### English

- Removed the decorative rotation from the homepage position card so the card and board align cleanly with the page grid.
- Updated static asset version parameters to prevent browsers from reusing the previous tilted style.

## [0.2.0-alpha.3] - 2026-09-17

### 中文

- 匿名交互记录新增独立的“复制 FEN”和“打开局面”按钮，可直接跳转 xiangqiai.com 复现研究。
- 新增公开开发者教程，提供 curl、Python、JavaScript 示例和响应消费约定。
- 新增明文只显示一次、6 分钟失效的随机临时 Key，并通过匿名 HMAC 来源指纹、单来源锁、全局容量和 Nginx 限流防滥用。

### English

- Added dedicated “Copy FEN” and “Open position” actions to every anonymous event row.
- Added a public developer guide with curl, Python, JavaScript, and response-handling examples.
- Added one-time-display random trial keys that expire after six minutes, protected by anonymous HMAC client fingerprints, per-client locking, a global capacity limit, and Nginx rate limiting.

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
