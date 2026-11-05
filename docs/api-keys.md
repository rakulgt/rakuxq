# Hosted key quotas / 托管 Key 次数额度

Existing time-only keys remain unchanged. Optional quotas are independent of expiry
and engine permissions. A metered key stops at either its usage limit or expiry.
Creating a quota does **not** grant engine access or commercial NNUE permission.

次数 Key 与原期限 Key 兼容，额度和有效期任一先到即停止。当前出招仍限维护者个人
测试白名单；次数功能不代表已经允许向付费客户提供受限 NNUE 出招。

## Counting / 计次

- One successful `/v1/solve` image-plus-move response costs **one** credit, not two.
- Accepted `/v1/recognitions` or `/v1/fen` costs one credit; successful nonempty
  move results from `/v1/analyses` or `/v1/solutions` also cost one.
- Review/rejected input, invalid parameters, permission errors, engine failure,
  partial success and terminal positions without a move cost zero.
- Separate client requests are separate calls. This is not an idempotency/retry
  contract; response delivery to a disconnected client cannot be guaranteed.
- 查询 `/v1/key-status`、健康检查、条款确认和网页 Lab 不扣次数。

Concurrent requests reserve credits atomically in SQLite before work. Failed work
releases its reservation. A crash leaves a held reservation for operator review;
do not expire it blindly while the original work may still complete. When all
remaining credits are in flight, HTTP 429 uses `API_KEY_QUOTA_BUSY`; permanently
spent quota uses `API_KEY_QUOTA_EXHAUSTED`. No response includes a plaintext key.

Metered response headers are `X-RakuXQ-Quota-Limit`, `-Used`, `-In-Flight` and
`-Remaining`. Remaining means available credits after subtracting completed and
currently reserved calls. Authenticated `GET /v1/key-status` returns the same quota
as JSON without spending a credit. Existing request parameters and result fields
are unchanged.

## Administration / 签发与核验

Use the installed key CLI with the production database and an **exclusive private
output file**, never ordinary stdout/logs/chat:

```text
python -m rakuxq_api.key_cli --database <private-key-db> create --label <owner-label> --days 365 --uses 500 --output <new-private-file>
python -m rakuxq_api.key_cli --database <private-key-db> status --id <key-id>
```

Omitting `--uses` preserves time-only behavior. `--output` refuses overwrites and
creates mode 0600 on Linux. The database stores hashes only; the private delivery
file contains the one-time key and must not enter source control. Key revocation
and expiry continue to apply before quota access. Trial keys do not gain engine
access or quota-management privileges.

The migration only adds `api_key_quotas` and `api_key_reservations` plus an index.
Back up the database before application startup. Rolling back to an older app
requires revoking newly issued metered keys first, since the old app cannot enforce
their quotas; do not overwrite the active key database with a stale backup.
