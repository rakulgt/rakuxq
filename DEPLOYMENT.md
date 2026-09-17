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
- 健康检查：`https://xq.rakubank.com/healthz`
- 密钥库：`/opt/raku/secrets/rakuxq/api-keys.sqlite3`
- 运行日志：journald 单元 `rakuxq-api`
- Nginx 日志：`/opt/raku/logs/rakuxq/`
- 备份：`/opt/raku/backups/rakuxq/`

上传图片只在请求处理期间使用，不进入项目资产、识别日志或训练数据。模型只读保存在
`/opt/raku/portable/rakuxq/models/`，来源与校验信息见 `models/manifest.json`。

## 首次与后续发布

本地必须使用已验证的 ONNX 权重、干净的 Git 工作区和已登记 SSH 别名：

```powershell
pwsh -NoProfile -File scripts/deploy.ps1
```

该入口会校验模型，通过 `git archive` 生成可追溯版本，在新版本目录安装 Python venv，校验
Nginx，原子切换 `current` 并执行回环健康检查。正式密钥库已存在时绝不会被本地副本覆盖。

首次 DNS 接入后执行 Certbot 签发；之后由已有 Certbot 自动续期机制管理。

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
- API Key 和密钥库不得进入 Git、聊天、普通日志或部署记录。

## 回滚

发布失败时脚本会尽量将 `current` 恢复到原版本。手工回滚时，把 `current` 软链接指向上一个
`releases/<git-revision>`，重启 `rakuxq-api.service`，再验证回环与公网健康检查。Nginx 和 systemd 配置的变更前副本位于
`/opt/raku/backups/rakuxq/<timestamp>-<revision>/`。
