---
artifact_id: rakuxq.native.readme
version: 0.1.0-experimental
status: experimental
license: MIT
production_approved: false
---

# RakuXQ 独立核心 / Independent core

这是独立实现的候选核心，不是当前线上引擎的更名版本，也不是已经达到 Pikafish 棋力的替代品。
当前生产接口、视觉模型、搜索预算和引擎保持原样；终端不需要修改脚本。

## 当前能力与边界

- C++17、标准库运行时、独立棋盘表示、合法走子、将军和零合法着法终局检查。
- 迭代加深 Alpha-Beta、静态搜索、捕获/缓存走法排序、时间/节点/深度约束、异步 stop、UCI MultiPV 1/2。
- 自定义 `RAKUXQ_NNUE_V1` 小型量化评估：1262 特征、32 隐藏单元、增量累加器。不是 Pikafish 权重格式。
- 从随机初始化训练，只接受本核心独立生成且带摘要、来源、到期信息的合成自对弈资料；下一轮自对弈可加载有匹配训练回执的自有模型。
- 复核分组与训练按整盘隔离，交叉分组重复局面从训练侧剔除；保留浮点/量化损失，但不把损失下降说成棋力上升。
- 标准开局和随机可达局面的差分测试使用固定 BSD-2-Clause `xiangqi.js` 作为外部规则判据；不把判据实现移入核心。
- 搜索中的重复保护不等于正式长将/长捉裁决；竞技场遇到重复或步数上限记为未裁定，不虚构和棋或胜负。
- **尚未完成：**同预算棋力不退步证明、完整历史裁决、自有视觉模型与独立盲测、生产资源对照与灰度切换。

元信息、来源声明、模型摘要和 CI 记录只构成工程证据，不是无侵权法律认证。代码由项目独立编写并使用 AI 辅助；未导入第三方引擎实现或权重。普通运行库和测试依赖仍遵守其自身许可证。

## 构建和验证

在项目根目录执行，构建输出不要放进本组件源码树：

```powershell
cmake -S packages/rakuxq-engine -B tmp/native-build -DCMAKE_BUILD_TYPE=Release
cmake --build tmp/native-build --config Release --parallel 1
# Windows 多配置构建通常位于 tmp/native-build/Release/rakuxq-engine.exe
$env:RAKUXQ_NATIVE_ENGINE = (Resolve-Path tmp/native-build/Release/rakuxq-engine.exe).Path
python -m pytest packages/rakuxq-engine/tests -q
node packages/rakuxq-engine/tools/differential.mjs $env:RAKUXQ_NATIVE_ENGINE
python packages/rakuxq-engine/tools/contracts.py
python packages/rakuxq-engine/tools/metadata.py --receipt tmp/native-source-receipt.json
```

Python 工具使用现有 API 开发环境（含 NumPy、pytest、Ruff）。Linux 可执行文件位于 `tmp/native-build/rakuxq-engine`。CI 同时构建和测试 Linux/Windows；没有本机二进制时，部分测试会明确跳过，不能据此宣称 native 测试通过。

## 有界训练实验

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
python packages/rakuxq-engine/tools/pipeline.py generate --engine $env:RAKUXQ_NATIVE_ENGINE --games 8 --plies 48 --time-ms 10 --output tmp/own-selfplay.jsonl
python packages/rakuxq-engine/tools/pipeline.py train --data tmp/own-selfplay.jsonl --epochs 20 --output tmp/own-candidate.rknn
# 继续一轮自有模型生成与重新训练；新候选必须另行评测，绝不自动上线。
python packages/rakuxq-engine/tools/pipeline.py generate --engine $env:RAKUXQ_NATIVE_ENGINE --network tmp/own-candidate.rknn --games 8 --plies 48 --time-ms 10 --output tmp/own-next-selfplay.jsonl
python packages/rakuxq-engine/tools/pipeline.py train --data tmp/own-next-selfplay.jsonl --epochs 20 --output tmp/own-next-candidate.rknn
```

工具拒绝覆盖已有文件；生成数据时的棋力标签来自弱的自有搜索，不是最佳着法真值。遇到步数上限的对局结果为 `null`，不是伪造的和棋。首阶段最多载入 20,000 行，训练库尚不接收客户上传、短期审计或外部教师标签；客户训练采集仍关闭。数据到期信息最长三年，训练入口拒绝过期资料；正式大规模存储与清理服务仍待实现。

固定种子、二进制与数据摘要使实验可追溯；固定时间搜索受硬件和调度影响，不承诺跨硬件逐字一致。模型/资料/回执留在忽略的 `tmp/` 或受控私有存储，不进入 Git。

## 自动新旧对照

```powershell
python packages/rakuxq-engine/tools/arena.py --candidate $env:RAKUXQ_NATIVE_ENGINE --candidate-network tmp/own-candidate.rknn --reference $env:RAKUXQ_NATIVE_ENGINE --pairs 4 --plies 120 --time-ms 100 --output tmp/own-arena.json
```

同一开局交换红黑，单线程、固定 Hash 与相同预算，两引擎串行搜索。先与自有旧版比较，许可核验后才可另选第三方评测对手；竞技场证据明确仅用于评测，不作为训练教师标签。

报告记录二进制/网络摘要、开局和逐手完整招法、最终 FEN、终局或未裁定原因、响应时间和探索性区间。未裁定不是和棋，少量对局不是 Elo 认证，报告始终不授予生产替换权。正式替换还需识图盲测、足量同预算对弈、历史规则、资源与稳定性、回滚验证及来源审查。

## 客户端兼容

`contracts/v1-client-baseline.json` 冻结现有五个公开接口的请求体、默认值、鉴权头和成功媒体类型。新增测试使用现有 API 适配器真实运行独立二进制，核验中文招法、固定红方评分、终局和主要返回字段。不增加客户端必填参数，不改变 FEN 空格、auto 约定或搜索预算。

## English

This is an independently authored, AI-assisted experimental engine, not a renamed upstream engine and not a proven production replacement. It includes legal move generation, bounded iterative search, a small independently initialized quantized evaluator, offline synthetic selfplay/training, paired evaluation, source metadata checks, and a frozen public-request baseline.

Production vision, engine, authentication and client contracts remain unchanged. Generated parameters are not based on official Pikafish weights. The external BSD rules oracle is verification-only. Bootstrap-label loss is not playing strength; repetition/ply limits are unresolved outcomes, not fabricated draws. No production promotion command exists. Customer-data training remains disabled, and full engine/vision parity still requires independent evidence.
