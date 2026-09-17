# RakuXQ 模型目录

模型权重不直接提交 Git。当前 ONNX provider 预期：

```text
models/
├─ pose.onnx
└─ layout.onnx
```

当前已取得并本地验证的首个基线：

- 项目：`yolo12138/Chinese_Chess_Recognition`
- 上游演示：https://huggingface.co/spaces/yolo12138/Chinese_Chess_Recognition
- 代码镜像：https://github.com/cheese2020/Chinese-Chess-Recognition
- 上游声明许可证：MIT
- 建议候选文件：`onnx/pose/4_v6-0301.onnx`、`onnx/layout_recognition/nano_v3-0319.onnx`

固定模型版本为 `cchess-baseline-2025-03-19`，文件大小和 SHA-256 见 `manifest.json`。权重仍由 `.gitignore` 排除，不随源码仓库分发。

该上游公开校验结果报告的整盘零错误率约为 `0.83`，所以它只作为 RakuXQ 的可运行基线，不代表第一版准确率目标已经实现。RakuXQ 对紧裁截图和保留背景的实拍分别尝试 `1.25`、`1.5` 两种关键点尺度，选择几何合法且分数更高的结果。当前 `0.55` 棋盘关键点阈值对应上游关键点乘积分数约 `0.30`；所有阈值都必须在 RakuXQ 自有盲测集上重新校准。

RakuXQ 的公开源码版本不包含或重新分发这些权重；使用者按上游项目说明自行取得模型文件。本项目仍需继续复核权重许可链、训练数据来源并建立自有盲测结果。在完成这些工作及生产安全配置前，不提供由 RakuXQ 维护者背书的公网托管服务或模型权重发布包。
