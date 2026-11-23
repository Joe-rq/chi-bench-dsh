# 申请已经提交，为什么仍然得零分？

我们先前猜测，医疗流程 Agent 容易在事情办完前宣布结束。对 CHI-Bench 两组公开执行记录的复盘，把问题缩小到了一个更早的决定：**这份申请现在应该建包并提交，还是应该补证或停止提交？**

这是对公开基线的独立复盘。DSH 和 ReJev 在本研究中都还没有运行。逐题证据、检查项、关键动作的步骤号和原始运行链接见 [pairs.csv](pairs.csv)。

## 样本与配对

取主办方 Claude Code 和社区 Erius 两个公开提交包的全部 Provider PA 任务。两包均标注模型为 Claude Opus 5、数据版本为 chi-bench-v1.0.0、评审模型为 Claude Opus 4.7。每个配置每题运行一次。以 result.json 中完整的 task_name 连接，共 25 对、50 条轨迹。样本按提交包和赛道选取，保留了两边都成功和都失败的任务。

| Claude Code | Erius | 同名任务数 |
|---|---|---:|
| 通过 | 通过 | 4 |
| 失败 | 通过 | 14 |
| 通过 | 失败 | 1 |
| 失败 | 失败 | 6 |

Claude Code 通过 5/25，Erius 通过 18/25。25 对的 task_checksum 全部不同。两包的运行配置和提供给 Agent 的指导也有差异，Erius 的提交说明披露了按任务提供的指导信息。相同名称和版本标签不能证明两边运行了逐字节相同的任务。这 13 单的净差只描述这两个包；它不能度量单独更换 Harness 的效果。

## 主要发现

Claude Code 失败的 20 单里，有 17 单未通过评分项 `provider_pre_submission.packet_absent`（该任务要求申请包不存在）。这 17 单里，15 条轨迹显式调用了提交工具。14 个“Claude Code 失败、Erius 通过”的配对里，有 13 个包含该评分项失败。每单可以同时失败于其他检查，包括服务地点、程序编码和最终状态。以上数字不能当作阻止提交就能挽回的单数。

**T015 能看清问题发生的时刻。** Claude Code 在第 24 步建包，第 25 步调用提交，工具回执把案件状态置为 `submitted`。它最后告诉用户“已提交”，与回执一致，但官方只通过了 7/12 项检查。Erius 在第 37 步记录 `do_not_submit`，返回状态 `closed`，通过了 12/12。若检查器只在最终回复时核对“有没有提交回执”，它会放过这条确实已提交、却走错业务分支的记录。

## 五个案例，十条轨迹

下表有意选了典型分歧、反向分歧和边界案例。频次统计以上方 25 对全量样本为准。括号内为评分卡通过项数 / 适用项数，步骤号取自公开 ATIF 轨迹。

| 任务 | Claude Code | Erius | 对检查器的启示 |
|---|---|---|---|
| T008 | 第 22 步建包、23 步提交（6/11） | 第 46 步记录补证（11/11） | 补证是有效业务结果，应允许本轮在该分支结束。 |
| T015 | 建包并成功提交（7/12） | 记录不提交并关闭（12/12） | 工具调用成功只能证明系统执行了这个动作。 |
| T013 | 第 20 步记录提交决定，21 步提交（13/13） | 第 45 步选补证，仅案件状态检查失败（12/13） | 这是反向案例，一律拦截提交会伤及原本通过的任务。 |
| T022 | 第 26 步提交，程序编码和服务申请评审未通过（10/12） | 第 54 步提交；57 步再记录决定时工具报错，整单仍通过（12/12） | 提交方向相同仍可能填错字段；一次工具报错也不能直接充当整单失败标签。 |
| T036 | 第 19 步建包，21 步记录不提交；申请包和服务地点检查失败（10/12） | 第 33 步记录不提交，轨迹无建包调用（12/12） | 只观察最后一次决策会漏掉之前已写入的申请包。 |

以下每行的两个链接都指向固定 Git 提交中的原始试次目录。评分见 `verifier/scorecard.json`，动作与工具返回见 `agent/trajectory.jsonl.zst`。

- T008　[Claude Code](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider/pa_t008_t008_o002_p01_new_referr__A4k3RFX) · [Erius](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider/pa_t008_t008_o002_p01_new_referr__XZaP2QC)
- T013　[Claude Code](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider/pa_t013_t013_o002_p01_new_referr__pV5xTMx) · [Erius](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider/pa_t013_t013_o002_p01_new_referr__qM5x53S)
- T015　[Claude Code](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider/pa_t015_t015_o002_p01_new_referr__ExaH25t) · [Erius](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider/pa_t015_t015_o002_p01_new_referr__uMBGi4s)
- T022　[Claude Code](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider/pa_t022_t022_o001_p01_new_referr__bs7gSPu) · [Erius](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider/pa_t022_t022_o001_p01_new_referr__7P5ydJA)
- T036　[Claude Code](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider/pa_t036_t036_o002_p01_new_referr__xHyoAoP) · [Erius](https://github.com/actava-ai/leaderboard/tree/86ef971ff809f037dd4c502d099733b7dc23f9b2/benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider/pa_t036_t036_o002_p01_new_referr__i7dEpjA)

## 留给 ReJev 的实验

第一个待测节点放在 Agent **首次准备创建申请包之前**。输入仅含该时刻可见的任务、业务材料与工具返回，候选动作是“允许建包 / 补充证据 / 记录不提交”。证据不足以独立定性的节点单独标注。先让两种方法盲判同一批节点：一条只检查明确缺项的规则，以及已有的 ReJev-2B。另将 Agent 原决策作为参照。一并统计误放与误拦，后者可用 T013 说明。

本报告读过的 25 个任务均属探索集。后续验证要预留独立案例；同一任务的改写或重跑仍放在同一组。评分卡、后续动作和另一系统的成功结论仅用于事后核查。要回答哪种方法真的改善整单表现，还需在固定版本、相同输入和预算下运行原版 DSH 与介入版，报告救回、误伤和新增成本。本次未评估在线效果。

## 复算

需要 Git、Python 3 和 zstd。下面的命令在本项目根目录运行，只检出相关的上游提交包。脚本从两组试次的 reward、scorecard、result 和压缩轨迹重建表格；CSV 只保留计数、检查名、选定动作和证据链接。动作栏记录调用尝试，具体是否成功以工具回执为准。

```bash
git clone --filter=blob:none --no-checkout https://github.com/actava-ai/leaderboard.git ../chi-leaderboard
git -C ../chi-leaderboard sparse-checkout set \
  benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider \
  benchmarks/chi-bench/submissions/2026-07-26-erius-opus5/trials/pa_provider
git -C ../chi-leaderboard checkout --detach 86ef971ff809f037dd4c502d099733b7dc23f9b2
python3 studies/provider-pa-01/reproduce.py ../chi-leaderboard /tmp/chi-pa-pairs.csv
diff -u studies/provider-pa-01/pairs.csv /tmp/chi-pa-pairs.csv
```
