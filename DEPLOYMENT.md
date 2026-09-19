# RakuXQ 生产部署

## 已登记拓扑

- 正式域名：`xq.rakubank.com`
- 服务器：`raku-cn-prod-01` (`1.117.71.5`)
- 部署根：`/opt/raku/portable/rakuxq`
- 版本目录：`/opt/raku/portable/rakuxq/releases/<git-revision>`
- 当前版本：`/opt/raku/portable/rakuxq/current`
- systemd：`rakuxq-api.service`
- 回环端口：`127.0.0.1:8040`
- 公网入口：`https://xq.rakubank.com/v1/recognitions`
- 棋局实验室：`https://xq.rakubank.com/lab`
- 标准 FEN 入口：`https://xq.rakubank.com/fen/<standard-fen>`
- 健康检查：`https://xq.rakubank.com/healthz`
- 密钥库：`/opt/raku/secrets/rakuxq/api-keys.sqlite3`
- 临时 Key 来源指纹秘密：`/opt/raku/secrets/rakuxq/trial-key-pepper`
- 运行日志：journald 单元 `rakuxq-api`
- Nginx 日志：`/opt/raku/logs/rakuxq/`
- 匿名统计库：`/opt/raku/logs/rakuxq/public-metrics/public-metrics.sqlite3`
- 备份：`/opt/raku/backups/rakuxq/`

已鉴权调用的上传原图和完整交互记录短期保存在
`/opt/raku/logs/rakuxq/interactions/`，用于早期准确率和稳定性分析。每条记录含原图、请求参数、
完整响应、状态码、耗时和 Key ID，不含明文 API Key；12 小时后由
`rakuxq-audit-retention.timer` 自动删除，磁盘占用达到 2 GiB 时优先删除最旧记录。记录不会进入
Git、永久样本集或自动训练集。模型只读保存在 `/opt/raku/portable/rakuxq/models/`，来源与校验
信息见 `models/manifest.json`。

匿名统计库跨版本保留：单条事件在 72 小时后删除，`public_totals` 只保存累计数字。该目录由
`rakuxq` 专用用户以 `0700` 访问，不得随发布清空。官网根路径和 `/api/public/stats` 无需 API Key，
但公开响应不得出现客户或请求标识。`rakuxq-metrics-backup.timer` 每天使用 SQLite 在线备份创建
一致性快照，保存到 `/opt/raku/backups/rakuxq/metrics/` 并自动删除超过 30 天的旧快照。

## 首次与后续发布

本地必须使用已验证的 ONNX 权重、干净的 Git 工作区和已登记 SSH 别名：

```powershell
pwsh -NoProfile -File scripts/deploy.ps1
```

该入口会校验模型，通过 `git archive` 生成可追溯版本，在新版本目录安装 Python venv，校验
Nginx，原子切换 `current` 并执行回环健康检查。正式密钥库已存在时绝不会被本地副本覆盖。

首次 DNS 接入后执行 Certbot 签发；之后由已有 Certbot 自动续期机制管理。发布脚本检测到
`/etc/letsencrypt/live/xq.rakubank.com/` 后会自动安装 TLS 版 Nginx 配置，不会在后续发布中
覆盖或丢失源站 HTTPS。

Apple 快捷指令公开分享地址通过服务器环境变量 `RAKUXQ_SHORTCUT_URL` 设置，只允许
`https://www.icloud.com/shortcuts/...`；未设置时官网显示“即将开放”。分享的快捷指令不得包含 Key。

公开开发文档位于 `/developers`。`POST /api/public/trial-keys` 签发 6 分钟测试 Key；部署脚本首次
发布时生成独立 pepper 文件，后续发布保留原值且不输出内容。临时签发使用 HMAC 来源指纹、同一
来源单活、最多 100 个全局活跃 Key 和 Nginx IP 突发限流。该入口不得写入 access log 的请求体或
返回明文 Key；响应必须禁止缓存。

`xq.rakubank.com` 当前使用 Cloudflare **仅 DNS（灰云）**，直接解析到已登记源站，以避免中国大陆
客户端上传图片时绕行境外 Cloudflare 节点。客户端直接使用源站 Let's Encrypt 证书建立 HTTPS；
Cloudflare 的 SSL/TLS 模式在仅 DNS 状态下不参与本域名传输。切回代理模式前必须重新进行上传延迟、
真实客户端 IP、限流和 HTTPS 验收。

## API Key 运营

服务端只保存 Key 的 SHA-256 哈希。签发时明文只显示一次：

```bash
/opt/raku/portable/rakuxq/current/.venv/bin/python -m rakuxq_api.key_cli \
  --database /opt/raku/secrets/rakuxq/api-keys.sqlite3 \
  create --label "customer-name" --days 365
```

查看非敏感元数据、续期和吊销：

```bash
python -m rakuxq_api.key_cli --database /opt/raku/secrets/rakuxq/api-keys.sqlite3 list
python -m rakuxq_api.key_cli --database /opt/raku/secrets/rakuxq/api-keys.sqlite3 renew --id <key-id> --days 365
python -m rakuxq_api.key_cli --database /opt/raku/secrets/rakuxq/api-keys.sqlite3 revoke --id <key-id>
```

官方托管标准为 `39 元人民币/年`，续费联系微信 `lgtqcn`。收款后使用 `renew` 延长原 Key；只有泄露或主动更换时才重新签发。

## 容量与安全边界

- 单 Uvicorn worker，ONNX Runtime 两线程，避免在 4 核 3.6 GiB 主机上与其他产品抢占资源。
- systemd `MemoryMax=1200M`；Nginx 限制单请求约 13 MiB、每 Key 每分钟 30 次、突发 10 次、并发 2 次。
- `/healthz` 不要求 API Key；`/v1/recognitions` 和 `/v1/fen` 必须鉴权。
- `/` 与 `/api/public/stats` 公开访问，只提供官网资源和匿名指标。
- `/developers` 与 `/api/public/trial-keys` 公开访问；后者只签发 6 分钟、不可续期的测试 Key。
- API Key 和密钥库不得进入 Git、聊天、普通日志或部署记录。
- 短期审计只保存有效 Key 的调用；匿名、无效、过期或吊销 Key 的请求不保存请求体。
- `rakuxq-audit-retention.timer` 每分钟清理一次过期审计，并触发项目访问日志的小时级轮转；
  原图和交互目录保留上限为 12 小时。

## 回滚

发布失败时脚本会尽量将 `current` 恢复到原版本。手工回滚时，把 `current` 软链接指向上一个
`releases/<git-revision>`，重启 `rakuxq-api.service`，再验证回环与公网健康检查。Nginx 和 systemd 配置的变更前副本位于
`/opt/raku/backups/rakuxq/<timestamp>-<revision>/`。
