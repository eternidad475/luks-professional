#!/usr/bin/env python3
"""歯科臨床向け CLI: 審美的主訴のオート判定・推奨治療提示・術前術後シミュレーション。

使い方の例:

    # 主訴の一覧（コード）を表示
    python dental.py --list-complaints

    # 評価用シーケンス（複数枚）をモーフィング動画化 + 審美評価
    python dental.py --macro-eval f1.jpg f2.jpg f3.jpg --micro-eval t1.jpg t2.jpg \
        --case-id C001 -o report/

    # 評価用 + 術後イメージ（シミュレーション動画も生成）
    python dental.py --macro-eval face_now.jpg --macro-target face_goal.jpg -o report/

    # ブラウザでスマホ直接撮影 / 一眼レフ画像アップロードする Web UI を起動
    python webapp.py  # → http://localhost:8000

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
    # 評価用画像シーケンス（複数枚・順序つき）
    p.add_argument("--macro-eval", nargs="+", default=None,
                   help="マクロ評価用画像シーケンス（顔貌・スマイル、複数可）")
    p.add_argument("--micro-eval", nargs="+", default=None,
                   help="ミクロ評価用画像シーケンス（歯・歯肉の接写、複数可）")
    # シミュレーション用（術後イメージ・任意）
    p.add_argument("--macro-target", help="マクロ術後イメージ（シミュレーション用）")
    p.add_argument("--micro-target", help="ミクロ術後イメージ（シミュレーション用）")
    # 後方互換エイリアス（単一画像）
    p.add_argument("--macro-before", help="(エイリアス) --macro-eval の単一画像")
    p.add_argument("--macro-after", help="(エイリアス) --macro-target")
    p.add_argument("--micro-before", help="(エイリアス) --micro-eval の単一画像")
    p.add_argument("--micro-after", help="(エイリアス) --micro-target")
    p.add_argument("--before", help="(エイリアス) --macro-eval の単一画像")
    p.add_argument("--after", help="(エイリアス) --macro-target")
    p.add_argument(
        "--complaints",
        default="",
        help="術者が確定した主訴コード（カンマ区切り）。例: crowding,discoloration",
    )
    auto = p.add_mutually_exclusive_group()
    auto.add_argument("--auto", dest="auto", action="store_true",
                      help="マクロ/ミクロの自動評価を有効化（既定）")
    auto.add_argument("--no-auto", dest="auto", action="store_false",
                      help="自動評価を無効化（主訴は手動指定のみ）")
    p.set_defaults(auto=True)
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

    # 評価用シーケンス（--*-eval 優先、無ければ単一エイリアスから構成）
    macro_eval = args.macro_eval or [p for p in (args.macro_before, args.before) if p][:1] or None
    micro_eval = args.micro_eval or ([args.micro_before] if args.micro_before else None)
    macro_target = args.macro_target or args.macro_after or args.after
    micro_target = args.micro_target or args.micro_after

    if not any([macro_eval, micro_eval, macro_target, micro_target]):
        print("エラー: 評価用またはシミュレーション用の画像が必要です。", file=sys.stderr)
        print("       例: --macro-eval f1.jpg f2.jpg / --micro-eval t1.jpg", file=sys.stderr)
        print("       主訴の一覧は `python dental.py --list-complaints`。", file=sys.stderr)
        return 2

    codes = [c.strip() for c in args.complaints.split(",") if c.strip()]

    try:
        run_case(
            macro_eval=macro_eval,
            micro_eval=micro_eval,
            macro_target=macro_target,
            micro_target=micro_target,
            complaints=codes,
            auto=args.auto,
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
