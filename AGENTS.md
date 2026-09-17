# RakuXQ Agent Instructions

本文件是工作区根 `AGENTS.md` 的薄型项目适配层。产品事实、当前进度和部署事实不在此重复维护。

## 任务入口

- 产品范围：`PROJECT.md`
- 人类运行与验证入口：`README.md`
- 当前完成度：`docs/handoffs/CURRENT.md`
- 生产部署：`DEPLOYMENT.md`（涉及部署时）
- 项目注册：`../../registry/projects.yaml`

## 项目特有执行约束

- 用户上传的棋盘图片默认只在内存中处理，不写入日志、样本集或持久存储。
- `models/` 中的第三方权重必须有来源、版本、许可证和校验和记录；无法追溯的权重不得发布。
- 不得以规则修正掩盖视觉识别错误；原始候选、置信度和修正原因必须可审计。
- 遵守 `PROJECT.md` 中“范围、边界与持久不变量”定义的拒识优先原则。

## 最低验证门槛

- 纯领域逻辑变更至少运行 `python -m unittest discover -s tests -v`。
- API 或推理变更还需运行健康检查、上传接口冒烟测试，并记录所用模型版本。
- 模型变更必须报告整盘零错误率、自动通过覆盖率和自动通过结果精确率，不能只报告单格准确率。

## 生产限制

- 正式域名为 `xq.rakubank.com`，生产目标为 `raku-cn-prod-01`，部署根为 `/opt/raku/portable/rakuxq`；必须使用 `DEPLOYMENT.md` 和版本化脚本。
- `/opt/raku/secrets/rakuxq/` 中的 API Key 哈希库和环境文件不得打印、下载到项目或被新部署覆盖。
- 常规已验证修改默认完成本地测试、GitHub 同步、生产发布和公网冒烟；更换域名、价格、密钥库或超出 RakuXQ 范围的共享配置仍需明确授权。

## GitHub 发布授权

- 本项目的独立公开仓库固定为 `https://github.com/rakulgt/rakuxq`，默认分支为 `main`，许可证为 MIT。
- 用户已明确授权当前及后续常规开源交付闭环：在本项目内创建聚焦提交、推送 `main`、创建和推送版本标签、创建 GitHub Release，并更新仓库说明与常规项目元数据；无需为同类操作重复询问。
- 用户已明确授权将精确路径 `D:/github/rakubank.com/projects/rakuxq` 加入当前 Windows 用户的 Git `safe.directory`，用于沙箱与 Administrator 账户之间的正常发布协作；不得把父目录、工作区根或通配路径加入信任。
- 上述授权不包含强制推送、覆盖远端历史、改变仓库可见性、改远端所有者、删除 Release/仓库、发布第三方 ONNX 权重、上传用户图片或任何秘密；这些动作仍需单独确认。
