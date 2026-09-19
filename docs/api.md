# RakuXQ API v1

官方托管地址：`https://xq.rakubank.com`。视觉客户端默认调用完整 JSON 接口
`POST /v1/recognitions`，仅在 `status` 为 `accepted` 时消费 `fen` 字段。实验性引擎接口
可在配置了本地引擎的自托管环境使用；官方托管服务尚未部署受限 NNUE 权重。

## 标准 FEN 网页入口

任何两字段或六字段中国象棋 FEN 都可以直接拼接到固定前缀，打开 RakuXQ Lab：

```text
https://xq.rakubank.com/fen/3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4%20w
```

地址只需要把 FEN 中的空格编码为 `%20`；浏览器与 Apple 快捷指令通常会自动完成。网页也兼容
`/#/<FEN>` 和 `/lab?fen=<FEN>`。两字段输入会在需要调用引擎时规范化为六字段形式，API Key
必须继续通过 `Authorization` 或 `X-API-Key` 请求头传递，禁止加入 URL。

## 鉴权与有效期

官方托管服务的识别接口要求每位客户使用独立 API Key，二选一传入：

```http
Authorization: Bearer <api-key>
```

或：

```http
X-API-Key: <api-key>
```

未提供或无效 Key 返回 `401`，已吊销或过期 Key 返回 `403`。过期响应包含
`API_KEY_EXPIRED` 以及续费信息：微信 `lgtqcn`，`39 元人民币/年`。明文 Key 只在
签发时显示一次，服务端只保存 SHA-256 哈希。

官网 [`/developers`](https://xq.rakubank.com/developers) 可匿名申请测试 Key。测试 Key 随机生成、
明文只显示一次、有效期 6 分钟且不可续期；同一来源在有效期内不能重复领取。领取入口不保存原始
IP，只保存服务器秘密加盐后的不可逆 HMAC 指纹。使用测试 Key 上传的图片仍遵循下文 12 小时
短期审计政策。长期或生产调用请使用独立年度 Key。

## `GET /healthz`

返回服务与识别 provider 是否就绪。`status=degraded` 表示 HTTP 服务可用但模型不可用。

## `GET /api/public/stats`

无需 API Key。返回历史累计成功交互数、自动通过数、最近 72 小时汇总、小时趋势和匿名事件流。
事件只包含 `occurred_at`、`status`、`fen`、`confidence`、`duration_ms`；不包含原图、Key/Key ID、
IP、文件名、请求 ID 或设备信息。单条事件 72 小时后删除，历史累计数字继续保留。

## `POST /api/public/trial-keys`

无需 API Key，也不需要请求体。成功时返回一次性可见的 `api_key`、`expires_at` 和
`expires_in_seconds=360`，响应强制 `Cache-Control: no-store`。同一来源已有有效临时 Key 时返回
`429 TRIAL_KEY_ALREADY_ACTIVE`；服务容量达到保护上限时返回 `503`。

## `POST /v1/recognitions`

请求为 `multipart/form-data`：

- `image`：必填，当前支持 JPEG、PNG、WebP；Apple 快捷指令建议先转换为 JPEG。
- `side_to_move`：接受 `red|w|%20w`、`black|b|%20b` 或 `unknown`，默认
  `unknown`。`%20w/%20b` 专门兼容需要把同一菜单值直接拼入棋谱 URL 的 Apple 快捷指令；
  服务端会将其规范化为红方或黑方。
- `orientation`：`auto|red_bottom|black_bottom`，默认 `auto`。

响应状态：

- `accepted`：置信度和局面校验通过。
- `review_required`：存在未知格、低置信度或阻断性局面警告。

核心位置字段：

- `piece_placement`：仅包含 10 行棋子布局。
- `fen`：面向快捷指令与棋谱网站的简化值，严格为
  `piece_placement + 一个真实空格 + w/b`，例如 `4k4/9/.../5K3 w`。
- `full_fen`：为后续引擎保留的完整六字段形式，例如 `4k4/9/.../5K3 w - - 0 1`。

调用方应当使用以下等价逻辑：

```text
if response.status == "accepted":
    result = response.fen
else:
    result = ""
```

不要在 `review_required` 时仅因 `fen` 字段非空就自动进入 NNUE 计算。
未找到棋盘或无法解码图片时，接口直接返回非 2xx 错误；`rejected` 状态保留给后续可审计拒识响应。

局部棋盘遵循项目约定：将完整 9×10 网格投影回原图后，交叉点中心位于画面外的格子默认无子。响应通过以下字段披露规则补空：

- 顶层 `assumed_empty_cells`：按最终 FEN 方向给出 `{rank,file}` 坐标。
- 顶层 `grid`：应用全部“默认空”规则后的最终 10×9 局面。
- `prediction.cells[].visible=false` 与 `assumed_empty=true`：标记单格来源。
- `prediction.cells[].raw_symbol`：保留规则覆盖前的模型原始候选，便于审计。
- `prediction.cells[].refinement` 与 `raw_confidence`：披露同图视觉原型纠正及纠正前置信度。
- `warnings` 包含非阻断警告 `UNSEEN_CELLS_ASSUMED_EMPTY`。

已经进入画面但模型原始类别为未知 `x` 的格子，按产品规则补空，原因记录为 `visually_uncertain`，并增加非阻断警告 `UNCERTAIN_CELLS_ASSUMED_EMPTY`。低置信度的明确棋种不再自动补空：provider 会尝试用同图中高置信、同色棋子作为视觉原型进行保守纠正，成功时增加 `SAME_IMAGE_PROTOTYPE_REFINEMENT`，并在 `prediction.metadata.prototype_refinements` 中保存原类别、纠正类别、相似度、次优相似度及原型坐标；无法纠正时保留候选并返回 `review_required`。部分棋盘中低置信空位采用单独的放宽门槛，触发时增加 `PARTIAL_EMPTY_CONFIDENCE_RELAXED`。棋盘延伸到画面外时，竖屏快速路径会自动恢复双尺度定位。

## `POST /v1/fen` 兼容接口

参数与识别接口相同。仅在结果为 `accepted` 且行棋方已知时返回 `text/plain` 简化 FEN，格式
严格为 `piece_placement + 空格 + w/b`；否则返回非 2xx JSON 错误。此端点仅作兼容保留；
新客户端应使用 `/v1/recognitions`。

成功响应同时包含以下可审计响应头：

- `X-RakuXQ-Request-Id`：本次识别请求 ID。
- `X-RakuXQ-Provider`：实际执行识别的程序 provider。
- `X-RakuXQ-Model-Version`：实际模型版本；正式部署不得使用 `unverified`。
- `X-RakuXQ-Warnings`：包括部分棋盘补空等非阻断警告，无警告时为 `none`。
- `X-RakuXQ-Assumed-Empty-Cells`：用 `rank,file` 列出规则补空位置，无补空时为 `none`。
- `X-RakuXQ-Assumed-Empty-Details`：用 `rank,file:reason` 区分 `out_of_frame` 与 `visually_uncertain`。

服务没有人工或大模型兜底路径。模型未就绪时必须返回 `503`，不能根据文件名、历史答案或手工输入返回 FEN。

## `POST /v1/analyses`

将已经确认的中国象棋 FEN 提交给可配置的本地引擎。请求体为 JSON：

```json
{
  "fen": "3aka3/9/9/4C4/4n4/9/9/4C4/9/4K4 w",
  "movetime_ms": 500
}
```

`fen` 可以使用 RakuXQ 两字段简化形式或六字段形式；服务端发送给引擎前统一转换为六字段。
`movetime_ms` 默认 500，当前允许 50–3000 毫秒。接口返回 ICCS 最佳着法、ponder、主要变化、
深度、节点、耗时和引擎/权重身份。

评分始终以红方为固定视角，与当前行棋方无关：正整数表示红优，负整数表示黑优，`0` 表示近似
均衡。`score.display` 直接使用 `+186`、`-243`、`0`；强制杀棋使用 `KO(+N)` 表示红方绝杀，
`KO(-N)` 表示黑方绝杀。`value` 始终保留带正负号语义的整数，便于程序比较。

## `POST /v1/solve`

参数是在 `/v1/recognitions` 基础上增加 `movetime_ms`。服务先执行真实视觉识别；只有结果为
`accepted` 且行棋方已知时，才把 `full_fen` 送入引擎。响应同时包含：

- `fen`：快捷指令已经使用的简化 FEN；
- `recognition`：完整、可审计的原识别结果；
- `analysis`：最佳着法、红方视角整数评分、PV 和可复现引擎信息。

识别需要复核或被拒绝时，`analysis` 为 `null`，不得静默对不可靠局面给出着法。未配置引擎返回
`503 ENGINE_NOT_CONFIGURED`；非法 FEN、分析超时和引擎异常分别返回明确的机器错误码。

## 官方托管短期审计

为评估早期准确率、稳定性和失败模式，官方托管服务对**有效 API Key** 的调用保存原始上传文件、
表单参数、完整响应、HTTP 状态、耗时、请求 ID 和 Key ID。明文 Key 不记录；无效、过期、吊销或
缺少 Key 的请求不保存请求体。每条记录最长保存 12 小时，达到 2 GiB 容量上限时会更早删除最旧
记录。短期审计不构成永久数据集或训练授权，也不会进入 Git。
