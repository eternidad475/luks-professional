#!/usr/bin/env python3
"""歯科臨床向け CLI: 審美的主訴のオート判定・推奨治療提示・術前術後シミュレーション。

使い方の例:

    # 主訴の一覧（コード）を表示
    python dental.py --list-complaints

    # 術前/術後画像から、オート判定 + 推奨治療 + シミュレーション動画 + レポート
    python dental.py --before pre.jpg --after post.jpg --case-id C001 -o report/

    # 術前のみ。オート判定に手動主訴を追加してレポート作成
    python dental.py --before pre.jpg --complaints crowding,discoloration -o report/

    # オート判定を切り、主訴を手動指定
    python dental.py --before pre.jpg --no-auto --complaints missing_tooth -o report/

注意: 出力は記録・患者説明・シミュレーションの補助を目的とした参考情報であり、
確定診断・治療方針の決定を代替するものではありません。
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from morph_video.dental import DISCLAIMER, list_complaints, run_case
from morph_video.dental.treatments import recommend
from morph_video.morphers import MORPHERS


def _print_complaints() -> None:
    print("審美的主訴の一覧（--complaints にコードをカンマ区切りで指定）:\n")
    cat = None
    for c in list_complaints():
        if c.category != cat:
            cat = c.category
            print(f"［{cat}］")
        auto = " ★オート判定対応" if c.auto_detectable else ""
        print(f"  {c.code:28s} {c.label}{auto}")
        # 提示しうる治療カテゴリの要約
        rec = recommend(c.code)
        cats = sorted({o.category for o in rec.options})
        tag = "・".join(cats) if cats else "（矯正・補綴の適応外）"
        print(f"  {'':28s}   → {tag}")
    print(f"\n{DISCLAIMER}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dental.py",
        description="歯科 審美シミュレーション/記録 ツール（矯正・補綴の推奨提示）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--list-complaints", action="store_true", help="主訴コード一覧を表示して終了")
    p.add_argument("--before", help="術前画像")
    p.add_argument("--after", help="術後 / 術後シミュレーション画像")
    p.add_argument(
        "--complaints",
        default="",
        help="術者が確定した主訴コード（カンマ区切り）。例: crowding,discoloration",
    )
    auto = p.add_mutually_exclusive_group()
    auto.add_argument("--auto", dest="auto", action="store_true", help="オート判定を有効化（既定）")
    auto.add_argument("--no-auto", dest="auto", action="store_false", help="オート判定を無効化")
    p.set_defaults(auto=True)
    p.add_argument(
        "--auto-min-confidence",
        type=float,
        default=0.35,
        help="オート判定で採用する最小信頼度",
    )
    p.add_argument("--case-id", default="", help="症例 ID")
    p.add_argument("--patient", default="", help="患者ラベル（イニシャル等、個人情報に注意）")
    p.add_argument("-o", "--output-dir", default="report", help="出力フォルダ")

    # シミュレーション動画オプション
    sim = p.add_argument_group("シミュレーション動画")
    sim.add_argument("-m", "--method", choices=list(MORPHERS), default="flow", help="モーフィング方式")
    sim.add_argument("--fps", type=float, default=30.0, help="出力 FPS")
    sim.add_argument("--transition", type=float, default=1.5, help="1 遷移あたりの秒数")
    sim.add_argument("--hold", type=float, default=1.0, help="各画像を静止表示する秒数")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_complaints:
        _print_complaints()
        return 0

    if not args.before and not args.after:
        print("エラー: --before か --after のいずれかが必要です。", file=sys.stderr)
        print("       主訴の一覧は `python dental.py --list-complaints`。", file=sys.stderr)
        return 2

    codes = [c.strip() for c in args.complaints.split(",") if c.strip()]

    try:
        run_case(
            before=args.before,
            after=args.after,
            complaints=codes,
            auto=args.auto,
            auto_min_confidence=args.auto_min_confidence,
            case_id=args.case_id,
            patient_label=args.patient,
            output_dir=args.output_dir,
            method=args.method,
            fps=args.fps,
            transition_seconds=args.transition,
            hold_seconds=args.hold,
            progress=lambda msg: print(msg),
        )
    except KeyError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2

    print(f"\n{DISCLAIMER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
