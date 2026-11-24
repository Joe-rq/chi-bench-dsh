# 建包前的复核能改变哪一步？

T013 和 T015 是两个方向相反的已知案例。在公开 Claude Code 轨迹中，T013 建包后通过全部 13 项检查。T015 同样建了包，只通过 12 项中的 7 项，其中一项要求最终无包。在这两份草稿上，ReJev 恰好都给出了值得质疑的建议。我们用它们测试业务系统在何时收到写请求，以及人能否从轨迹还原这次决定。[公开评分及轨迹](../provider-pa-01/README.md) · [离线预测](../provider-pa-02/model_replay.csv)

| 本地配对 | 无提示时角色服务收到的动作 | ReJev 意见 | 遵从提示的脚本随后执行 | 审计单 |
|---|---|---|---|---|
| T013 | 建包一次 | 补证 | 记录补证决定，建包零次 | [T013](T013-local.md) |
| T015 | 建包一次 | 放行 | 再次调用建包，实际建包一次 | [T015](T015-local.md) |

四次运行使用真实 DSH SDK。本地脚本提供主模型回复和角色服务，提示组使用真实 MiniCPM5-2B + ReJev clean-r16 在 CPU 推理。两份草稿均来自公开轨迹中首次建包前的表单写入，推理时模型只能看到申请说明和最多六个问卷字段。每题的提示哈希与动作都和研究 02 的冻结记录一致。角色服务记录的写入与 DSH 导出的 ATIF 分别核对。完整病案、政策条款和评分卡均未进入复核提示。

**本地结果说明提示可以先于业务写入送达。** 脚本按预设规则采纳建议。在 T013，这会放弃一次历史上成功的建包；在 T015，错误建包仍然发生。两题均经过挑选，不能从这里估算自主 DeepSeek 会采纳多少建议，或整单通过率。当前正式沙盒成绩待测。

## 干预发生在哪里

基线把 DSH 直接接到当前角色的 MCP 服务。提示组在同一端点前增加转发进程。首次调用建包时，它暂缓写入，将复核意见作为工具返回值交还主模型。主模型可补证、记录决定，也可再次调用建包。后续建包直接转发。复核只作用于这条工具路径，单次提示允许主模型覆盖。权重进程按需启动，审计单的复核耗时含加载。首次提示也会增加一次主模型决策机会，因此两组差异同时包含暂停和意见内容的影响。

## 本地复现

从仓库根目录执行。准备 Python 3.12、uv、zstd、固定版本的[公开轨迹](../provider-pa-01/README.md#复算)及[两份权重快照](../provider-pa-02/README.md#复现)。设置 `CHI_SOURCE` 指向 leaderboard checkout，`CHI_REJEV_BASE` 和 `CHI_REJEV_ADAPTER` 分别指向两份完整权重目录。运行时只使用本地模型文件。

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -e '.[smoke]' harbor==0.20.0 mcp==1.26.0
uv venv --python 3.12 .venv-rejev
uv pip install --python .venv-rejev torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv-rejev transformers==5.6.2 peft==0.21.0 accelerate==1.16.0
out=$(mktemp -d)/pair
.venv/bin/python studies/provider-pa-03/local_pair.py "$CHI_SOURCE" "$out" \
  "$PWD/.venv-rejev/bin/python" "$CHI_REJEV_BASE" "$CHI_REJEV_ADAPTER"
python studies/provider-pa-03/audit.py "$out/t013/baseline" "$out/t013/advice" --local-fixture
python studies/provider-pa-03/audit.py "$out/t015/baseline" "$out/t015/advice" --local-fixture
```

## 官方沙盒配对

按[项目安装步骤](../../README.md#运行一项官方任务)准备固定版本的 CHI-Bench、角色镜像、授权手册、官方任务和执行／评审配置。将 `CHI_OFFICIAL` 设为上游 checkout，`CHI_PA_TASKS` 设为包含两道 Provider PA 任务目录的父目录。在运行进程的环境中设置执行与评审密钥、两个权重目录。提示组在试次容器内安装独立的 CPU 推理环境，并校验宿主机权重；宿主机需有空间传入约 5 GB 权重。两组使用上游支持的下划线工具名分隔符，保持同一套工具名称。

```bash
out=$(mktemp -d)/official
python studies/provider-pa-03/official_pair.py "$CHI_OFFICIAL" "$CHI_PA_TASKS" "$out" --environment docker
```

也可使用已配置的 Modal 后端，将参数改成 `--environment modal`。运行器固定两题、两组、每组每题一次，同用 `deepseek-v4-pro`。每一对核对任务名、任务校验和、主模型、执行状态、官方 `scorecard.json` 与 `reward.json`，然后在任务输出目录生成 `audit.md`。未记录的费用保留为空缺。这个规模允许逐案比较，估计 pass^3 需要每题至少三次独立运行。原始事件和模型文本保存在运行目录，公开展示时仅使用裁剪后的审计单。
