"""Render a Markdown comparison from completed run artifacts, without raw case text."""

import argparse
import json
from pathlib import Path

BUNDLE = "docs_create_submission_bundle"
FORM = "forms_save_form_response"


def read(path):
    return json.loads(path.read_text())


def cell(value):
    return str(value).replace("|", "／").replace("\n", " ")


def load(trial, arm, local):
    (attempt,) = (trial / "agent").glob("dsh-*/execution.json")
    meta = read(attempt)
    if meta["execution"] != "completed" or meta.get("review", "none") != arm:
        raise ValueError(f"Incomplete or mismatched arm at {trial}")
    trace = read(trial / "agent/trajectory.json")
    calls = [
        (s["step_id"], c["function_name"].split("__")[-1], c["tool_call_id"])
        for s in trace["steps"]
        for c in s.get("tool_calls", [])
    ]
    log = attempt.parent / "review.jsonl"
    events = (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )
    notices = [e for e in events if e["event"] == "notice"]
    first = next((s for s, n, _ in calls if n == BUNDLE), None)
    if any(e["event"] == "scorer_failure" for e in events) or len(notices) != int(
        arm == "rejev-advice" and first is not None
    ):
        raise ValueError("Incomplete advisory evidence")
    evidence = [f"步骤 {s}" for s, n, _ in calls if n == FORM and first and s < first]
    notice = notices[0] if notices else None
    tag = "脚本化角色服务" if local else "官方模拟器"
    data = {
        "执行引擎和主模型": "DSH + 本地脚本化主模型"
        if local
        else "DSH / " + meta["model"],
        "首次建包尝试": f"轨迹步骤 {first}" if first else "未调用",
        "此前表单写入尝试": "、".join(evidence) or "未记录",
        "此前病历检索或证据操作": "、".join(
            f"步骤 {s} {n}"
            for s, n, _ in calls
            if first
            and s < first
            and (
                n.startswith("chart_")
                or n in ("docs_upload_evidence", "docs_list_case_documents")
            )
        )
        or "未见相关角色工具调用",
        "政策条款或证据充分性": "此版本只读表单草稿，无可核对的政策引用",
        "ReJev 复核意见": notice["action"] if notice else "未触发",
        "复核耗时（秒，含加载权重）": notice["seconds"] if notice else "—",
        "复核输入 SHA-256": notice["prompt_sha256"] if notice else "—",
        "复核后下一业务工具": next(
            (
                n
                for s, n, _ in calls
                if first
                and s > first
                and n.startswith(("auth_", "docs_", "forms_", "cases_", "chart_"))
            ),
            "未再调用",
        )
        if notice
        else "—",
        "工具调用总数（含复核返回）": len(calls),
    }
    if local:
        fixture = read(trial / "local.json")
        data[tag + "收到的写操作"] = " → ".join(fixture["writes"])
        data["官方评分"] = "未运行"
        data["API 调用费用"] = "无外部计费调用"
        return (fixture["task"], "fixture", meta["model"]), data
    result = read(trial / "result.json")
    card = read(trial / "verifier/scorecard.json")
    reward = read(trial / "verifier/reward.json")["reward"]
    if (
        result.get("exception_info")
        or type(reward) not in (int, float)
        or reward not in (0, 1)
        or reward != card["binary_reward"]
        or not result.get("task_checksum")
    ):
        raise ValueError("Missing or inconsistent verifier evidence")
    data["官方评分"] = (
        f"{reward:g}（{card['passed_checks']}/{card['total_checks']} 项）"
    )
    data["未通过的检查"] = "、".join(card["failed_checks"]) or "无"
    data["申请包应不存在检查"] = card["checks"].get(
        "provider_pre_submission.packet_absent", "不适用"
    )
    cost = (result.get("agent_result") or {}).get("cost_usd")
    data["主 Agent 费用（USD）"] = cost if cost is not None else "无计费记录"
    return (result["task_name"], result["task_checksum"], meta["model"]), data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline", type=Path)
    p.add_argument("advice", type=Path)
    p.add_argument("--local-fixture", action="store_true")
    args = p.parse_args()
    left, a = load(args.baseline, "none", args.local_fixture)
    right, b = load(args.advice, "rejev-advice", args.local_fixture)
    if left != right:
        p.error("Task identity, checksum or primary model differ")
    print(f"# {left[0]}\n")
    print(
        (
            "本地集成验证。DSH 和 ReJev 使用真实运行时，主模型和业务服务由脚本模拟。"
            if args.local_fixture
            else f"CHI-Bench 官方沙盒配对记录。任务校验值为 `{left[1]}`。"
        )
        + "\n"
    )
    print("| 检查项 | 无提示 | ReJev 提示 |\n|---|---|---|")
    for key in a:
        print(f"| {key} | {cell(a[key])} | {cell(b[key])} |")


if __name__ == "__main__":
    main()
