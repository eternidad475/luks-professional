#!/usr/bin/env python3
"""歯科臨床向け CLI: 審美的主訴のオート判定・推奨治療提示・術前術後シミュレーション。

使い方の例:

    # 主訴の一覧（コード）を表示
    python dental.py --list-complaints

    # マクロ(顔貌・スマイル)とミクロ(歯・歯肉)の術前/術後からレポート一式を生成
    python dental.py --macro-before face_pre.jpg --macro-after face_post.jpg \
        --micro-before teeth_pre.jpg --micro-after teeth_post.jpg --case-id C001 -o report/

    # マクロ術前のみ + 手動主訴
    python dental.py --macro-before face_pre.jpg --complaints crowding,discoloration -o report/

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
    # マクロ（顔貌とスマイル）
    p.add_argument("--macro-before", help="マクロ術前画像（顔貌・スマイル）")
    p.add_argument("--macro-after", help="マクロ術後 / シミュレーション画像")
    # ミクロ（歯と歯肉）
    p.add_argument("--micro-before", help="ミクロ術前画像（歯・歯肉の接写）")
    p.add_argument("--micro-after", help="ミクロ術後 / シミュレーション画像")
    # 後方互換: --before/--after はマクロのエイリアス
    p.add_argument("--before", help="(エイリアス) --macro-before と同じ")
    p.add_argument("--after", help="(エイリアス) --macro-after と同じ")
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

    macro_before = args.macro_before or args.before
    macro_after = args.macro_after or args.after

    if not any([macro_before, macro_after, args.micro_before, args.micro_after]):
        print("エラー: マクロ/ミクロのいずれかの画像が必要です。", file=sys.stderr)
        print("       例: --macro-before face.jpg / --micro-before teeth.jpg", file=sys.stderr)
        print("       主訴の一覧は `python dental.py --list-complaints`。", file=sys.stderr)
        return 2

    codes = [c.strip() for c in args.complaints.split(",") if c.strip()]

    try:
        run_case(
            macro_before=macro_before,
            macro_after=macro_after,
            micro_before=args.micro_before,
            micro_after=args.micro_after,
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
