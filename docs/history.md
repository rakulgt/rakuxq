# RakuXQ 项目源流 / Project History

## 中文

RakuXQ 的发起人李国泰（rakulgt，<lgt@rakubank.com>）出生于 1983 年。1988 年，五岁的
他学会中国象棋；1990 年获得村级象棋比赛冠军，1996 年获得中学校园冠军，2001 年进入大学
校级比赛前十名。棋手经历使他长期关注一个问题：人的局面判断和计算过程，能否被清晰地表达
为程序？

2006 年，李国泰开始系统学习 C++。2008 年，他开发了象棋推理引擎 **lgtXQ**，使用手工
线性评估函数衡量局面，并以 Alpha-Beta 搜索寻找着法。这一阶段把长期积累的棋感拆解为棋子
价值、位置、结构、攻守关系和搜索剪枝等可执行规则。

2018 年，新一代引擎采用 **RakuXQ** 名称，并转向 NNUE 神经网络评估函数与新一代
Alpha-Beta 搜索体系。它代表项目从“人工写出所有评估知识”转向“高效神经网络评估与成熟
博弈搜索协同”的技术升级。

2023 年，项目加入局面视觉识别原型，目标是消除真实棋盘、手机截图与象棋引擎之间的手工
录入步骤。2026 年，这条路线进一步演进为当前公开版本：一个本地推理、可审计、可通过
Apple 快捷指令调用的图片转 FEN HTTP API。

当前开源仓库首先把视觉识别阶段做成稳定基础设施。历史 RakuXQ 引擎不会以未经整理的私有
代码形式直接投入首版；后续阶段将通过明确的局面契约重新接入 NNUE 解题能力，提供最佳着法、
候选变化和终端推送。由此，RakuXQ 形成一条连续路线：

```text
棋手经验 → 手工评估 + Alpha-Beta → NNUE + 搜索 → 视觉识别 → 图片到解法
```

## English

RakuXQ was initiated by Li Guotai (rakulgt, <lgt@rakubank.com>), born in 1983. He learned
Xiangqi at the age of five in 1988, won a village championship in 1990, won his middle-school
campus championship in 1996, and placed in the top ten of a university tournament in 2001.
Those years of play led to a long-running question: can human position judgment and calculation
be expressed clearly as software?

Li began systematic C++ study in 2006. In 2008 he built **lgtXQ**, a Xiangqi engine using a
handcrafted linear evaluation function and Alpha-Beta search. This work translated practical
chess knowledge into executable concepts such as piece values, placement, structure, attack,
defence, and search pruning.

In 2018 the next-generation engine adopted the **RakuXQ** name and moved toward NNUE evaluation
and a newer Alpha-Beta search architecture. The change marked a shift from encoding every
evaluation insight by hand to combining efficient neural evaluation with mature game-tree search.

In 2023 the project added a visual position-recognition prototype to remove manual transcription
between physical boards, mobile screenshots, and the engine. In 2026 that line evolved into the
current public release: a local, auditable image-to-FEN HTTP API callable from Apple Shortcuts.

The open-source repository starts by making the vision stage dependable infrastructure. Historical
private engine code is not dropped uncurated into the first release; a later phase will reconnect
NNUE solving through a stable position contract and expose best moves, principal variations, and
terminal delivery. The result is one continuous path:

```text
player experience → handcrafted evaluation + Alpha-Beta → NNUE + search
                  → visual recognition → image to solution
```
