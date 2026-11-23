# CHI-Bench × DeepSeek Harness

在 CHI-Bench 的医疗业务环境里运行 DeepSeek 官方 Harness（DSH），保存每一步工具调用，再由 CHI-Bench 判定业务是否完成。当前以服务方事前授权为首个实验方向。

**进度**　已在本地验证真实 DSH 运行时能发现并调用角色 MCP 工具，读取返回值，完成会话，并将工具调用与结果导出为 Harbor 可验证的 ATIF 轨迹。该测试使用本地脚本模拟模型和业务服务。官方任务实测和成绩待补。

## 公开轨迹研究

[申请已经提交，为什么仍然得零分？](studies/provider-pa-01/README.md)　复盘两组公开基线的 25 对服务方事前授权任务。附逐题证据、五组案例和复算脚本。

## 复现本地测试

从本项目根目录运行。Python 3.12、uv、Git 和 SDK 支持的平台即可。首次安装需要联网，测试将请求发到本机回环地址。

```bash
uv venv --python 3.12
uv pip install -e '.[smoke]' 'harbor==0.20.0'
.venv/bin/python -m unittest discover -s tests -v
```

测试用例让模拟模型调用 `case_status`。只有工具真的收到调用、模型在下一轮读到指定返回值，且轨迹中的调用 ID 和观察结果一致，测试才通过。测试里的 token 由模拟服务给出。

## 运行一项官方任务

固定版本为 CHI-Bench `9d5a48277d4f5867e70e171d9a670d4c1bd19b5a`、Harbor `0.20.0` 和 DSH SDK `0.2.2rc2`。在本项目根目录记录路径，然后进入独立的上游 checkout。

```bash
adapter_dir="$(pwd -P)"
git clone https://github.com/actava-ai/chi-bench.git ../chi-bench-upstream
cd ../chi-bench-upstream
git checkout --detach 9d5a48277d4f5867e70e171d9a670d4c1bd19b5a
uv sync --frozen --extra dev
uv pip install --python .venv -e "$adapter_dir"
.venv/bin/cb-dsh agent list
```

按固定版本的[上游入门指南](https://github.com/actava-ai/chi-bench/blob/9d5a48277d4f5867e70e171d9a670d4c1bd19b5a/README.md)配置 Docker、公开任务、获准使用的手册和评审凭据。将 `DEEPSEEK_API_KEY` 与官方评审需要的 `ANTHROPIC_API_KEY` 配置在本地。先确认数据和镜像就绪。

```bash
.venv/bin/cb data verify
.venv/bin/cb docker build
```

将下面的环境变量设为一个包含 `task.toml` 的 PA 单题目录，然后执行。这个入口复用上游的模拟器、角色工具、超时和判分逻辑。真实运行会产生模型及评审费用。

```bash
: "${CHI_TASK_DIR:?Set CHI_TASK_DIR to one installed PA task directory}"
test -f "$CHI_TASK_DIR/task.toml" &&
  .venv/bin/cb-dsh experiment run --dataset "$CHI_TASK_DIR" \
    --agent dsh --model deepseek/deepseek-v4-pro --environment docker
```

## 如何读一次运行

| 文件 | 用途 |
|---|---|
| `agent/dsh-*/execution.json` | DSH 版本、模型、会话和退出状态 |
| `agent/dsh-*/events.jsonl` | DSH 原始事件，包含角色工具调用与返回值 |
| `agent/trajectory.json` | Harbor ATIF v1.2 轨迹，含调用和观察结果的对应关系 |
| `verifier/scorecard.json` | 官方逐项验收，由 CHI-Bench 生成 |
| `verifier/reward.json` | 官方任务得分，由 CHI-Bench 生成 |

每次正式试验应记录数据修订、模型端点、预算、评审配置和试验次数。原始日志可能含受限手册内容，发布前审查和裁剪。仓库只包含自编的合成测试数据。

## 第一轮实验

1. 用一项 Provider PA 任务验证官方判分，把运行故障与业务失败分别记录。
2. 固定题目、模型端点、预算和评审，比较官方 OpenAI Agents SDK 与 DSH。两边的工具暴露、上下文处理和提示差异写入实验记录。
3. 从开发题的一条失败轨迹提出一个改动，例如验证补件是否仍在待办。冻结改动后，在预留任务上报告配对得失、工具调用数与成本。暂无实测提升数字。

[DSH SDK](https://github.com/deepseek-ai/deepseek-harness/tree/dsh-v0.2.2-rc.2/python/sdk) · [CHI-Bench](https://github.com/actava-ai/chi-bench) · [公开执行记录](https://github.com/actava-ai/leaderboard)
