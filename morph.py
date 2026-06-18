#!/usr/bin/env python3
"""複数の画像をモーフィングでつないで動画にする CLI。

使い方の例:

    # オプティカルフロー方式 (既定)
    python morph.py a.jpg b.jpg c.jpg -o out.mp4

    # 特徴点ベース方式 + ループ
    python morph.py imgs/ -m feature --loop -o out.mp4

    # クロスフェードで素早く確認
    python morph.py *.png -m crossfade --fps 24 -o out.mp4
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

from morph_video.easing import EASINGS
from morph_video.io_utils import expand_inputs
from morph_video.morphers import MORPHERS
from morph_video.pipeline import build_video


def _parse_size(value: Optional[str]) -> Optional[Tuple[int, int]]:
    if not value:
        return None
    try:
        w, h = value.lower().split("x")
        return (int(w), int(h))
    except Exception:  # noqa: BLE001
        raise argparse.ArgumentTypeError("--size は WxH の形式で指定してください (例: 1280x720)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="morph.py",
        description="複数画像をモーフィングで動画化するツール",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "inputs",
        nargs="+",
        help="画像ファイル / ディレクトリ / グロブ (2 枚以上)。順序がそのまま遷移順になる。",
    )
    p.add_argument("-o", "--output", default="morph.mp4", help="出力動画ファイル")
    p.add_argument(
        "-m",
        "--method",
        choices=list(MORPHERS),
        default="flow",
        help="モーフィング方式",
    )
    p.add_argument("--fps", type=float, default=30.0, help="出力 FPS")
    p.add_argument(
        "--transition", type=float, default=1.0, help="1 遷移あたりの秒数"
    )
    p.add_argument(
        "--hold", type=float, default=0.5, help="各画像を静止表示する秒数"
    )
    p.add_argument(
        "--size",
        type=_parse_size,
        default=None,
        help="出力解像度 WxH (既定: 先頭画像に合わせる)",
    )
    p.add_argument(
        "--easing",
        choices=list(EASINGS),
        default="ease_in_out",
        help="遷移のイージング",
    )
    p.add_argument(
        "--loop", action="store_true", help="末尾から先頭へ戻る遷移を追加 (ループ向け)"
    )
    p.add_argument(
        "--aspect", choices=["9:16", "4:5", "1:1", "16:9"], default=None,
        help="書き出しアスペクト比 (既定: 元画像のまま)",
    )
    p.add_argument(
        "--fill", choices=["blur", "white", "black"], default="blur",
        help="アスペクト変換時の余白の埋め方",
    )

    # 特徴点方式のオプション
    feat = p.add_argument_group("特徴点方式 (--method feature)")
    feat.add_argument("--max-features", type=int, default=2000, help="ORB 特徴点の最大数")
    feat.add_argument("--ratio", type=float, default=0.75, help="Lowe 比率テストの閾値")
    feat.add_argument(
        "--min-matches", type=int, default=12, help="この数未満ならクロスフェードに退避"
    )

    # フロー方式のオプション
    flow = p.add_argument_group("フロー方式 (--method flow)")
    flow.add_argument("--flow-winsize", type=int, default=25, help="Farneback の窓サイズ")
    flow.add_argument("--flow-levels", type=int, default=5, help="ピラミッド階層数")
    return p


def _morpher_kwargs(args: argparse.Namespace) -> dict:
    if args.method == "feature":
        return dict(
            max_features=args.max_features,
            ratio=args.ratio,
            min_matches=args.min_matches,
        )
    if args.method == "flow":
        return dict(winsize=args.flow_winsize, levels=args.flow_levels)
    return {}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    files = expand_inputs(args.inputs)
    if len(files) < 2:
        print(
            f"エラー: 画像が 2 枚以上必要です (見つかったのは {len(files)} 枚: {files})",
            file=sys.stderr,
        )
        return 2

    print(f"入力 {len(files)} 枚 / 方式: {args.method}")
    for f in files:
        print(f"  - {f}")

    build_video(
        inputs=files,
        output=args.output,
        method=args.method,
        fps=args.fps,
        transition_seconds=args.transition,
        hold_seconds=args.hold,
        size=args.size,
        easing=args.easing,
        loop=args.loop,
        morpher_kwargs=_morpher_kwargs(args),
        progress=lambda msg: print(msg),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
