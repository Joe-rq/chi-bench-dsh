# ReJev 能拦住错误建包吗？

我们把 CHI-Bench 公开 Claude Code 基线的 25 条轨迹逐条停在首次创建申请包前，用 ReJev clean-r16、同权重关闭 LoRA 的 MiniCPM5-2B 和必填缺项规则判断下一步。**ReJev 建议拦下了 17 个最终应无包任务中的 11 个，也拦下了 8 个最终需要包任务中的 6 个。** 这次结果支持先做复核提示，并继续检验模型能从哪些材料中判断此时该不该放行。

## 比赛轨迹上的建包决定

| 在首个建包节点的判断 | 17 个最终应无包任务中放行 | 17 个最终应无包任务中拦截 | 8 个最终需建包任务中放行 | 8 个最终需建包任务中拦截 |
|---|---:|---:|---:|---:|
| 原 Agent 的建包尝试 | 17 | 0 | 8 | 0 |
| 仅查必填缺项 | 17 | 0 | 8 | 0 |
| MiniCPM5-2B | 0 | 17 | 0 | 8 |
| ReJev clean-r16 | 6 | 11 | 2 | 6 |

Claude Code 在 25 个节点上均读到过表单验证信息，最近观察到的必填缺项数均为零。另一个公开包 Erius 的 25 条轨迹里有 6 条尝试建包，缺项规则也全部放行；另外 19 条没有触发这个检查点。模型比较限定在 Claude Code 的 25 条轨迹，避免同题重复计数。

在 T015，原 Agent 建包提交，评分要求无包，ReJev 仍放行。T013 最终确需建包，原 Agent 整单通过，ReJev 却要求补证。在原本会尝试建包的群体里，底座更是 25 次全部拦截。只报“拦住了多少”会把全拦策略排到第一。这里的两种模型都未接管 DSH，也没有改变模拟器终态；本实验尚不能估算整单通过率会增加多少。

## 自编案例的动作判断

18 道题里，各有 6 道应建包、应补证、应停止。下表取固定选项顺序。误放指应补证或停止却放行，误拦指题设已明确允许建包却选择补证或停止。

| 方法 | 三选一正确 | 误放 / 12 | 误拦 / 6 |
|---|---:|---:|---:|
| 全部放行 | 6/18 | 12 | 0 |
| 仅查必填缺项 | 9/18 | 9 | 0 |
| MiniCPM5-2B | 6/18 | 0 | 6 |
| ReJev clean-r16 | 10/18 | 3 | 2 |

原始底座在这个顺序下没有放行任何题，6 个本可建包的案例全被拦住。加入 LoRA 后放行了其中 4 个，同时误放了另外 3 个。与缺项规则相比，ReJev 三分类只多答对 1 题，但误放从 9 次降到了 3 次，代价是新增 2 次误拦。

轮换三次选项后，ReJev 分别答对 10、11、10 题，18 道中有 15 道三次选择了同一业务动作。底座分别答对 6、7、7 题，8 道始终选择同一动作。此处的样本量始终为 18。六组自编规则无法代表真实事前授权分布。

## 两组数据各自能回答什么

[官方任务目录](https://www.actava.ai/benchmarks/docs/tasks)列有 25 个服务方事前授权任务；[第一次复盘](../provider-pa-01/README.md)已经读过全部 25 题。本次对比赛轨迹的再分析用于定位同一组错误，不能充当独立任务上的验证。另写了 6 组、共 18 个英文案例，每组都包含允许建包、先补证、本队列停止建包三种情况。案例使用虚构的机构、额度或服务规则，包含日期边界、材料冲突、重复申请等场景。[题面与答案](cases.json)

合成实验在推理前固定题目、答案、提问和选项，模型仅收到当前一题的规则、材料和表单明确标缺的字段。每题用三个循环排列分别推理，把字母还原成动作。主要结果用预先指定的首个顺序，其余两个顺序衡量稳定性。每题的三次排列共享同一套事实。标签由题目设计者给定，样本仅覆盖六种规则，没有外部独立标注。[全部合成预测](predictions.csv)

比赛回放按首次调用 `docs_create_submission_bundle` 截断，同批次工具返回也不进入输入。缺项规则读取之前表单保存或验证工具返回的 `missing_required_fields`，逐表保留最近状态。模型读取之前保存表单时写入的申请说明（前 1,000 字符）和最先出现的最多六个问卷字段（各取最新值，前 120 字符）。这些是原 Agent 写入或尝试写入的摘要，可能继承它的错误。模型看不到整份病历、政策手册或评分卡。任务名仅用于事后对表，结果文件只发布输入摘要的哈希、token 数、动作和步骤号。所有决策均在离线 CPU 上计算。[模型回放记录](model_replay.csv) · [规则回放记录](replay.csv)

评分卡中适用的 `packet_absent` 表示整单最终应无包，适用的 `submission.service_request` 表示该单进入提交评分。后一类被模型拦下记为“潜在误拦”，因为终局要求建包不代表当时材料已齐。真实轨迹的“补证”和“停止”统一计为拦截。这个口径衡量候选动作，与干预后能否提高整单通过率还有一步。

## 复现

在本目录执行。合成实验用 Python 3.11、PyTorch 2.8.0+cpu、Transformers 5.6.2、PEFT 0.21.0、Accelerate 1.16.0，CPU BF16、SDPA、无采样。模型取 A/B/C 三个单 token 中 logit 最高的一项。底座对照在同一个模型对象上关闭 LoRA。两份权重已校验 SHA-256。硬件、精度或依赖变化可能改变个别边界决策。

| 权重 | 固定版本 | safetensors SHA-256 |
|---|---|---|
| [MiniCPM5-2B](https://huggingface.co/openbmb/MiniCPM5-2B) | `12a3808a956f869c767195e9266b59c4d21d92e2` | `14fb8e7f0a18d53d1f239773758bf581cee7e456a4523a54622c3a245b64402c` |
| [ReJev clean-r16](https://huggingface.co/joe-q/rejev-minicpm5-2b-choice) | `ca12f9df06ba1bc6a680b910e86190cfb6536d12` | `294b07beac96e42e4a69af41c1121bc2aa0a18cf4634ef2ea9e17b8032b9973e` |

先用标准库复核已发布的预测。需要重跑模型时，再在独立 Python 环境中安装依赖。首次运行从 Hugging Face 读取固定版本权重；也可用 `--base-dir` 和 `--adapter-dir` 指向相应的本地快照。按[第一次复盘的复算步骤](../provider-pa-01/README.md#复算)检出公开轨迹，并把下面的 `CHI_SOURCE` 设为该 checkout 的路径。

```bash
python summarize.py
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install transformers==5.6.2 peft==0.21.0 accelerate==1.16.0
python run.py /tmp/chi-synthetic.csv --threads 6
python replay.py "${CHI_SOURCE:?set CHI_SOURCE to the pinned leaderboard checkout}" /tmp/chi-rule.csv
python model_replay.py "$CHI_SOURCE" /tmp/chi-model.csv --threads 3
diff -u predictions.csv /tmp/chi-synthetic.csv
diff -u replay.csv /tmp/chi-rule.csv
diff -u model_replay.csv /tmp/chi-model.csv
```
