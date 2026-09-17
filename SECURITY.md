# Security Policy / 安全策略

## 中文

请不要在公开 Issue 中披露可利用的安全漏洞、凭据或用户图片。请通过 GitHub Security
Advisories 的私密报告功能联系维护者。RakuXQ 默认只在内存中处理上传图片；部署者仍需
自行配置 HTTPS、认证、限流、请求大小限制、超时和日志脱敏。

当前 `0.x` 版本为预发布版本，仅对最新发布版本提供安全修复。

官方托管服务的 API Key 只以 SHA-256 哈希保存。请把明文 Key 当作密码处理，不要提交到
Git、公开 Issue、聊天记录或客户端日志；泄露后应立即吊销并重新签发。

## English

Do not disclose exploitable vulnerabilities, credentials, or user images in public issues.
Please use GitHub Security Advisories to report vulnerabilities privately. RakuXQ processes
uploads in memory by default; deployers remain responsible for HTTPS, authentication, rate
limits, request-size limits, timeouts, and log redaction.

The `0.x` line is pre-release software. Security fixes are provided for the latest release only.

The hosted service stores only SHA-256 API-key hashes. Treat plaintext keys as passwords: never
commit them to Git or publish them in issues, chats, or client logs; revoke and rotate leaked keys.
