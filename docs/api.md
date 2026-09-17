# RakuXQ Vision API v1

官方托管地址：`https://xq.rakubank.com`。客户端默认调用完整 JSON 接口
`POST /v1/recognitions`，仅在 `status` 为 `accepted` 时消费 `fen`字段。

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

## `GET /healthz`

返回服务与识别 provider 是否就绪。`status=degraded` 表示 HTTP 服务可用但模型不可用。

## `POST /v1/recognitions`

请求为 `multipart/form-data`：

- `image`：必填，当前支持 JPEG、PNG、WebP；Apple 快捷指令建议先转换为 JPEG。
- `side_to_move`：`red|black|unknown`，默认 `unknown`。
- `orientation`：`auto|red_bottom|black_bottom`，默认 `auto`。

响应状态：

- `accepted`：置信度和局面校验通过。
- `review_required`：存在未知格、低置信度或阻断性局面警告。

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

参数与识别接口相同。仅在结果为 `accepted` 且行棋方已知时返回 `text/plain` FEN；否则返回非 2xx JSON 错误。此端点仅作兼容保留；新客户端应使用 `/v1/recognitions`。

成功响应同时包含以下可审计响应头：

- `X-RakuXQ-Request-Id`：本次识别请求 ID。
- `X-RakuXQ-Provider`：实际执行识别的程序 provider。
- `X-RakuXQ-Model-Version`：实际模型版本；正式部署不得使用 `unverified`。
- `X-RakuXQ-Warnings`：包括部分棋盘补空等非阻断警告，无警告时为 `none`。
- `X-RakuXQ-Assumed-Empty-Cells`：用 `rank,file` 列出规则补空位置，无补空时为 `none`。
- `X-RakuXQ-Assumed-Empty-Details`：用 `rank,file:reason` 区分 `out_of_frame` 与 `visually_uncertain`。

服务没有人工或大模型兜底路径。模型未就绪时必须返回 `503`，不能根据文件名、历史答案或手工输入返回 FEN。
