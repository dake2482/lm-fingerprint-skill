#!/usr/bin/env python3
"""lm-fingerprint skill 工具：基于 lmfpd SDK 的模型指纹检测。

子命令:
  challenges  生成官方采样挑战（3 条，写 challenges.json 并打印提示词）
  score       读取 answer-*.txt（或 samples.json），离线打分并输出报告
  probe       对第三方 API 端点做活体检测（需要 base-url/api-key/model）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import lmfpd
except ImportError:
    print("错误: 未安装 lmfpd。请运行: pip3 install lmfpd", file=sys.stderr)
    sys.exit(2)


def cmd_challenges(args: argparse.Namespace) -> int:
    workdir = Path(args.dir)
    workdir.mkdir(parents=True, exist_ok=True)
    challenges = lmfpd.generate_challenges(args.count)
    path = workdir / "challenges.json"
    path.write_text(json.dumps(challenges, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(challenges)} 条挑战 -> {path}")
    print()
    for i, c in enumerate(challenges, 1):
        print(f"========== 挑战 {i}（要求 {c['expected_count']} 个整数，1-355）==========")
        print(c["prompt"])
        print()
    print("下一步: 逐条凭第一反应回答（禁止使用任何工具/代码生成数字），")
    print("把三条回答的原始数字序列分别原样写入 answer-1.txt / answer-2.txt / answer-3.txt，")
    print("然后运行: score 子命令。")
    return 0


def _load_outputs(workdir: Path) -> list[dict]:
    samples_file = workdir / "samples.json"
    if samples_file.exists():
        data = json.loads(samples_file.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data:
            raise SystemExit(f"samples.json 必须是非空数组，每项含 text 和 expected_count: {samples_file}")
        return data
    challenges = json.loads((workdir / "challenges.json").read_text(encoding="utf-8"))
    outputs = []
    missing = []
    for i, c in enumerate(challenges, 1):
        answer = workdir / f"answer-{i}.txt"
        if not answer.exists():
            missing.append(str(answer))
            continue
        text = answer.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(str(answer) + " (空文件)")
            continue
        outputs.append({"text": text, "expected_count": c["expected_count"]})
    if missing:
        raise SystemExit("缺少回答文件或内容为空:\n  " + "\n  ".join(missing))
    return outputs


def _fmt_pct(p: float | None) -> str:
    return "  -  " if p is None else f"{p * 100:.1f}%"


def cmd_score(args: argparse.Namespace) -> int:
    workdir = Path(args.dir)
    outputs = _load_outputs(workdir)
    print(f"载入参考库（首次运行需下载数据，约 18MB，之后走缓存）...")
    detector = lmfpd.load()
    analysis = detector.analyze(outputs, strict=False)
    (workdir / "result.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 62)
    print("模型指纹检测结果 (lm-detector / lmfpd)")
    print("=" * 62)
    decision = analysis["decision"]
    if decision in ("scored", "partial"):
        tag = "完整排名（库内校准置信度）" if analysis.get("probability_status") == "reference_calibrated" else "完整排名（未校准）"
        if decision == "partial":
            tag = f"部分样本排名（{analysis['used_outputs']}/3 有效，无置信度）"
        print(f"结论: {analysis['prediction_name']}  (id: {analysis['prediction']})")
        print(f"家族: {analysis['family_prediction_name']}")
        if analysis.get("probability") is not None:
            print(f"置信度: {analysis['probability'] * 100:.1f}%（参考库内闭集概率）")
        print(f"模式: {tag}")
        print()
        print("候选排名（前 8）:")
        for r, item in enumerate(analysis["results"][:8], 1):
            print(f"  {r}. {item['display_name']:<28} score={item['score']:>8.3f}  p={_fmt_pct(item['probability'])}  [{item['family_name']}]")
    elif decision == "not_model":
        print("结论: 样本不像语言模型回答 —— 未生成排名。")
        print("原因: 相邻数字的变化方式与参考库中的语言模型回答不同。")
        print("常见于: 用代码/工具生成了数字、或对数字做了排序/打乱/去重。")
        print("处理: 请严格凭第一反应重新逐个给出数字，禁止调用任何工具。")
    else:  # unscorable
        print(f"结论: 暂不可评分 —— {analysis['used_outputs']}/3 条有效回答。")
        print("每条回答至少需要 max(80, 要求个数×55%) 个 1-355 范围内的整数。")

    print()
    print("样本诊断:")
    for d in analysis["diagnostics"]:
        status = "有效" if d["accepted"] else "无效"
        print(f"  样本 {d['index'] + 1}: 解析出 {d['parsed_numbers']} 个数字 "
              f"(最低要求 {d['minimum_numbers']}) -> {status}"
              + (f"，另有 {d['raw_out_of_range_count']} 个越界数字被忽略" if d["raw_out_of_range_count"] else ""))
    if analysis.get("sequence"):
        s = analysis["sequence"]
        print(f"  序列形态: lag-1 自相关 {s['autocorrelation']:.3f}, 小步占比 {s['small_step_share']:.3f}, "
              f"{'像模型回答' if s['model_like'] else '不像模型回答'}")
    print()
    print(f"参考库: built_at={detector.built_at}，完整结果已保存 -> {workdir / 'result.json'}")
    print("注意: 置信度是参考库内的闭集相对概率，不包含库外模型；未知模型只会得到“最接近”的候选，")
    print("      该结果是统计指纹证据，不构成身份证明。")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    if not (args.base_url and args.api_key and args.model):
        print("probe 需要 --base-url --api-key --model（或环境变量 BASE_URL/API_KEY/MODEL）", file=sys.stderr)
        return 2
    print(f"活体检测 {args.model} @ {args.base_url}（发送 3 条挑战，约 1-2 分钟）...")
    detector = lmfpd.load()
    result = detector.detect(args.base_url, args.api_key, args.model, api=args.api, timeout=args.timeout)
    if result.get("error"):
        print(f"错误: {result['error']}", file=sys.stderr)
        return 1
    analysis = result["analysis"]
    Path("probe-result.json").write_text(json.dumps(
        {"analysis": analysis, "samples": result["samples"]}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"结论: {analysis['prediction_name']}  置信度: {_fmt_pct(analysis.get('probability'))}")
    for r, item in enumerate(analysis["results"][:5], 1):
        print(f"  {r}. {item['display_name']:<28} p={_fmt_pct(item['probability'])}")
    print("详情已保存 -> probe-result.json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="lm-fingerprint 模型指纹检测工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ch = sub.add_parser("challenges", help="生成采样挑战")
    p_ch.add_argument("--dir", default="lmfpd-session", help="工作目录（默认 ./lmfpd-session）")
    p_ch.add_argument("--count", type=int, default=3, help="挑战条数 1-3（默认 3）")
    p_ch.set_defaults(func=cmd_challenges)

    p_sc = sub.add_parser("score", help="对已保存回答离线打分")
    p_sc.add_argument("--dir", default="lmfpd-session", help="工作目录")
    p_sc.set_defaults(func=cmd_score)

    p_pr = sub.add_parser("probe", help="对 API 端点活体检测")
    p_pr.add_argument("--base-url", default="")
    p_pr.add_argument("--api-key", default="")
    p_pr.add_argument("--model", default="")
    p_pr.add_argument("--api", default="responses", choices=["responses", "chatcompletion", "message"],
                      help="协议（默认 responses；OpenAI 兼容中转用 chatcompletion）")
    p_pr.add_argument("--timeout", type=float, default=120.0)
    p_pr.set_defaults(func=cmd_probe)

    args = parser.parse_args()
    if args.command == "probe":
        import os
        args.base_url = args.base_url or os.environ.get("BASE_URL", "")
        args.api_key = args.api_key or os.environ.get("API_KEY", "")
        args.model = args.model or os.environ.get("MODEL", "")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
