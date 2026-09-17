# Contributing / 参与贡献

## 中文

感谢你帮助改进 RakuXQ。适合贡献的方向包括棋盘定位、棋子分类、拒识与置信度校准、
匿名评测工具、Apple 快捷指令以及未来的 NNUE 引擎集成。

提交代码前请：

1. 不要提交用户图片、真实凭据、日志、模型权重或未经授权的数据集。
2. 为行为变化补充测试，并保留原始模型候选与自动修正依据。
3. 在 `apps/api` 中运行：

```powershell
python -m pytest -q
ruff check .
mypy src
```

视觉准确率改动应同时报告整盘零错误率、自动通过覆盖率和自动通过结果精确率，不能只
报告单格准确率。提交训练数据或模型前，请说明来源、授权、许可证、版本和校验和。

## English

Thank you for improving RakuXQ. Useful contribution areas include board localization,
piece classification, abstention and confidence calibration, privacy-safe evaluation,
Apple Shortcuts, and the future NNUE engine integration.

Before submitting code:

1. Do not commit user images, credentials, logs, model weights, or unlicensed datasets.
2. Add tests for behavior changes and preserve raw model candidates and correction evidence.
3. Run the following commands from `apps/api`:

```powershell
python -m pytest -q
ruff check .
mypy src
```

Accuracy changes should report exact-board accuracy, auto-accept coverage, and precision of
auto-accepted boards—not only per-cell accuracy. Any dataset or model contribution must
document provenance, consent, license, version, and checksums.
