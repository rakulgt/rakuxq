# Security Policy / 安全策略

## 中文

请不要在公开 Issue 中披露可利用的安全漏洞、凭据或用户图片。请通过 GitHub Security
Advisories 的私密报告功能联系维护者。RakuXQ 自托管默认只在内存中处理上传图片；部署者仍需
自行配置 HTTPS、认证、限流、请求大小限制、超时和日志脱敏。官方托管服务仅对已鉴权请求
保留最长 12 小时的原图和交互审计，用于早期质量分析；明文 API Key 不进入日志。
官网的公开统计与原图审计分离：单条公开记录只含时间、状态、简化 FEN、置信度和耗时，最长
72 小时；历史层只保留汇总计数，不公开 Key ID、IP、文件名、请求 ID 或设备信息。

当前 `0.x` 版本为预发布版本，仅对最新发布版本提供安全修复。

公开临时 Key 有效期固定为 6 分钟，明文只显示一次。同一来源有效期内只能领取一个；服务端以
秘密加盐 HMAC 保存不可逆来源指纹，不在临时 Key 表中保存原始 IP。临时 Key 调用仍属于有效鉴权
调用，因此适用 12 小时原图审计政策。

官方托管服务的 API Key 只以 SHA-256 哈希保存。请把明文 Key 当作密码处理，不要提交到
Git、公开 Issue、聊天记录或客户端日志；泄露后应立即吊销并重新签发。

## English

Do not disclose exploitable vulnerabilities, credentials, or user images in public issues.
Please use GitHub Security Advisories to report vulnerabilities privately. RakuXQ processes
uploads in memory by default; deployers remain responsible for HTTPS, authentication, rate
limits, request-size limits, timeouts, and log redaction. The official hosted service retains
authenticated originals and interaction audits for no more than 12 hours for early quality
analysis. Plaintext API keys are never logged.
Public metrics are separate from image audits. Public event rows contain only time, status,
simplified FEN, confidence, and latency for up to 72 hours; lifetime storage contains aggregate
counters only, never key IDs, IPs, filenames, request IDs, or device information.

The `0.x` line is pre-release software. Security fixes are provided for the latest release only.

Public trial keys expire after six minutes and are shown only once. One key may be issued per
client during that window. The service stores only a secret-keyed HMAC fingerprint for issuance
control, not the client's raw IP in the trial-key database. Trial-key calls remain authenticated
calls and therefore follow the 12-hour original-image audit policy.

The hosted service stores only SHA-256 API-key hashes. Treat plaintext keys as passwords: never
commit them to Git or publish them in issues, chats, or client logs; revoke and rotate leaked keys.
