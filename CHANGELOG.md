# Changelog / 更新日志

All notable changes to RakuXQ are documented here.

RakuXQ 的重要版本变化记录于此。

## [0.4.4-alpha.4] - 2026-09-26

### 中文

- 修复帅/将颜色锚点覆盖高置信原始分类的回归：真实案例中的红马、黑卒和红士不再被错误改成黑马、红兵和黑士。
- 在完成可靠字迹分割与多棋子一致性验证前，整块棋子图像的颜色比较降级为只读诊断；响应保留候选、距离和原始置信度，但明确标记 `applied=false`，不再修改 FEN。
- 新增对应 `N→n`、`p→P`、`A→a` 三连误改的回归测试，并保留帅/将身份不可变与方向旋转规则。

### English

- Fixed a regression where king-anchored colour matching overrode high-confidence raw classes, turning a real red horse, black pawn, and red advisor into the opposite camps.
- Downgraded whole-patch colour comparison to read-only diagnostics until reliable ink segmentation and multi-piece consensus exist; candidate matches, distances, and raw confidence remain auditable with `applied=false` but no longer mutate FEN.
- Added a regression test for the exact `N→n`, `p→P`, and `A→a` failure pattern while preserving immutable king identities and semantic board rotation.

## [0.4.4-alpha.3] - 2026-09-26

### 中文

- 新增 `xq-fast.rakubank.com` 免费 Cloudflare 橙云入口，为手机 VPN 和境外出口提供与国内直连入口独立的上传路线。
- 将单层子域名纳入 Nginx、源站证书和匿名分段计时；两个入口共享 API、鉴权、限流和短期审计规则。
- 停止把多层域名 `vpn.xq.rakubank.com` 作为免费代理入口，避免 Cloudflare Universal SSL 默认不覆盖导致的 TLS 握手失败。

### English

- Added `xq-fast.rakubank.com` as a free Cloudflare-proxied ingress for mobile VPN and overseas-exit upload paths, independent of the direct mainland-China ingress.
- Added the single-level hostname to Nginx, the origin certificate, and anonymous segmented timing while preserving the same API, authentication, rate limits, and short-lived audit policy.
- Retired multi-level `vpn.xq.rakubank.com` as a free proxy ingress to avoid TLS failures caused by the default Universal SSL hostname-depth limit.

## [0.4.4-alpha.2] - 2026-09-26

### 中文

- 修复 v0.4.4-alpha.1 的错误假设：帅、将字形身份不可互换；当帅在上、将在下且旋转后局面严格更合法时，执行180°坐标旋转而不是全盘交换红黑。
- 新增以帅、将棋子图像为本图红黑颜色锚点的保守阵营复核；只有锚点可分且目标棋子明显更接近其中一方时才修改其他已知棋子的大小写。
- 颜色传播永不改变帅、将、空位或未知格；原始类别、纠正步骤、颜色距离和方向决策全部保留用于审计。

### English

- Fixed the v0.4.4-alpha.1 assumption: the recognized identities of 帅 and 将 are immutable. When 帅 is above and 将 below and rotation strictly improves legality, coordinates rotate 180 degrees instead of swapping every camp.
- Added conservative image-local camp refinement using the 帅 and 将 patches as red/black colour anchors; another known piece changes case only when the anchors are separable and its colour is a decisive match.
- Colour propagation never changes either king, an empty cell, or an unknown cell, while raw classes, refinement steps, colour distances, and orientation decisions remain auditable.

## [0.4.4-alpha.1] - 2026-09-25

### 中文

- 新增象棋语义阵营纠错：方向归一化后若红帅、黑将成对落入对方九宫，并且交换红黑阵营可严格改善局面合法性，则自动纠正整盘棋子阵营。
- 纠正采用拒识优先策略；缺失主帅、单个主帅越界或交换后未改善时不触发，其他低置信与棋种问题仍返回 `review_required`。
- 完整保留模型原始网格、纠正原因及纠正前后阻断警告，并加入真实金色棋子皮肤失败案例回归测试。

### English

- Added a Xiangqi-aware camp correction: after orientation normalization, a whole-board red/black swap is applied only when both kings are cross-placed in the opposing palaces and the swap strictly improves position legality.
- Kept rejection-first behavior: missing kings, a single displaced king, or a non-improving swap never triggers correction, while unrelated low-confidence or piece-type issues still require review.
- Preserved the raw model grid, correction reason, and before/after blocking warnings, with a regression case derived from the real gold-disc visual-skin failure.

## [0.4.3-alpha.2] - 2026-09-24

### 中文

- 增加免费的 VPN/境外出口对照入口 `vpn.xq.rakubank.com`，与现有国内直连入口共享同一 API、鉴权、限流和短期审计规则。
- 源站证书和 Nginx 虚拟主机支持两个主机名；响应增加 `X-RakuXQ-Ingress`，匿名时序日志增加主机名，便于比较直连与 Cloudflare 免费代理路线。
- 保持 `xq.rakubank.com` 为 Cloudflare 灰云直连，不改变既有 Apple 快捷指令和 API 契约。

### English

- Added `vpn.xq.rakubank.com` as a free comparison ingress for VPN and overseas-exit clients, sharing the existing API, authentication, rate limits, and short-lived audit policy.
- Extended the origin certificate and Nginx virtual host to both names, added `X-RakuXQ-Ingress`, and included the hostname in anonymous timing logs for direct-versus-Cloudflare measurements.
- Kept `xq.rakubank.com` on DNS-only direct routing without changing the existing Apple Shortcut or API contracts.

## [0.4.3-alpha.1] - 2026-09-23

### 中文

- 图片接口增加标准 `Server-Timing` 响应头，直接区分请求体接收与应用处理耗时。
- 12 小时短期审计增加鉴权、请求接收、应用处理、响应发送和总耗时五段匿名指标，并记录请求体是否完整。
- Nginx 启用 HTTP/2，沿用现有 TLS 会话缓存；项目访问日志改为不含 IP、Key、查询参数和设备信息的专用分段耗时格式。
- 保持原有 JSON/FEN 契约、短期原图保留规则和推理模型不变。

### English

- Added the standard `Server-Timing` response header to image endpoints, separating request-body receipt from application work.
- Split the 12-hour audit timing into authentication, request receipt, application, response send, and total duration, with an explicit request-body completeness flag.
- Enabled HTTP/2 while retaining the existing TLS session cache, and switched project access logs to an anonymous timing format without IPs, keys, query strings, or device data.
- Preserved the existing JSON/FEN contracts, short-lived image retention policy, and inference model.

## [0.4.2-alpha.1] - 2026-09-19

### 中文

- 重新标定桌面棋盘尺寸：`1280×720` 下完整棋盘清晰可见，同时比上一版更接近专业棋谱工具的有效占屏比例。
- 顶部操作区升级为真正可用的菜单、新局、引擎执红、引擎执黑、分析模式、立即出招、变招、翻转、导入、保存/分享和编辑入口。
- “新局”改为单击立即回到标准三十二子开局，不再弹出二次选择；经典残局和空白摆子收纳到侧边菜单。
- 新增分组侧边菜单与桌面常驻主线招法轨，棋谱显示棋子、起点、终点、ICCS 和已有评分，并可直接跳转任一步。
- 压缩引擎面板的信息密度，评分、最佳着法、PV、深度、节点、耗时和引擎身份在同一屏内保持清晰响应。

### English

- Rebalanced the desktop board so the complete position remains visible at `1280×720` while using
  a more practical share of the screen.
- Made the top actions functional: menu, new game, engine as Red/Black, analysis mode, play now,
  variations, flip, import, save/share, and position editing.
- New Game now resets directly to the standard 32-piece start with one click; the classic puzzle
  and blank editor live in the side menu.
- Added a grouped side drawer and a persistent desktop main-line rail with navigable move details,
  ICCS, and available scores.
- Increased analysis-panel density without hiding engine evidence or licensing-safe unavailable states.

## [0.4.1-alpha.1] - 2026-09-19

### 中文

- 将 Lab 改造成适合常见 `1280×720` 桌面的一屏研究工作区，完整棋盘不再被首屏裁掉。
- 增加常驻高频工具栏：新局、开头、上一步、下一步、末尾、翻转、导入、保存/分享和编辑局面。
- “新局”现在真实回到三十二子标准开局；经典残局与空白摆子作为独立入口，不再与回到当前研究根节点混淆。
- 增加完整自由摆子流程：红黑十四种棋子、橡皮、清空、行棋方设置、将帅数量、九宫位置和照面校验，以及从编辑结果建立新 FEN。
- 导入对话框新增本地 JSON/TXT/FEN 文件读取；文件仍只在浏览器内处理，不上传服务器。
- 增加 Home/End 与左右方向键分支导航，并保留全部原有变化树、复制、JSON、PNG 和外部研究能力。

### English

- Reworked Lab into a compact single-screen workspace where a complete board fits a common
  `1280×720` desktop viewport.
- Added a persistent toolbar for new game, branch start/previous/next/end, flip, import,
  save/share, and position editing.
- A true new game now restores the standard 32-piece start; the classic puzzle and blank setup
  are separate, explicit actions.
- Added a real position editor with all 14 piece types, erasing, clearing, side-to-move selection,
  king count/palace/facing validation, and creation of a fresh FEN study.
- Added local JSON/TXT/FEN file import without uploading the selected file to the server.

## [0.4.0-alpha.1] - 2026-09-19

### 中文

- 新增公开 `/lab` 棋局实验室，以及可以直接拼接两字段或六字段标准 FEN 的
  `/fen/<FEN>` 固定入口。
- 兼容 `/#/<FEN>` 与 `/lab?fen=<FEN>`，无效局面显示可理解的错误而不是空白或 404。
- 增加响应式原生棋盘、红黑视角翻转、悔棋、重做、回合时间轴和不会因改走而丢失原线的变化树。
- 红方与黑方可分别选择关闭、只评分、最佳着法提示或自动代走；每个节点保留评分、PV、深度、
  节点、耗时、引擎版本和 NNUE SHA-256。
- 支持 FEN、ICCS 和 RakuXQ JSON 导入，支持复制 FEN/研究链接/ICCS、下载完整 JSON 和 PNG。
- 棋谱自动保存在浏览器本地；API Key 只存在于当前页面内存，不写入 URL、棋谱或永久存储。
- 官网入口、示例棋盘和缓存版本已指向 RakuXQ Lab；现有图片识别和 Apple 快捷指令 API 保持兼容。

### English

- Added the public `/lab` workspace and a fixed `/fen/<FEN>` route that accepts appended two-field
  or six-field standard Xiangqi FEN.
- Accepted `/#/<FEN>` and `/lab?fen=<FEN>` compatibility forms with understandable invalid-position
  errors instead of blank pages or 404 responses.
- Added a responsive native board, board flipping, undo/redo, a move timeline, and a
  non-destructive variation tree.
- Each side can independently disable assistance, request score-only or best-move hints, or let the
  engine move automatically; reproducibility metadata remains attached to each node.
- Added FEN, ICCS, and RakuXQ JSON import plus FEN/link/ICCS copy, complete JSON download, and PNG
  board export.
- Sessions recover from browser-local storage while API keys remain memory-only and never enter
  URLs, game records, or persistent browser storage.

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
