"""複数画像を順番にモーフィングでつないで 1 本の動画にするパイプライン。"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np

from .easing import get_easing
from .io_utils import VideoWriter, compute_aspect_size, fit_frame, load_and_normalize
from .morphers import Morpher, get_morpher


def _morph_pair(
    writer: VideoWriter,
    morpher: Morpher,
    img1: np.ndarray,
    img2: np.ndarray,
    transition_frames: int,
    easing: Callable[[float], float],
    include_last: bool,
) -> None:
    """img1 -> img2 の遷移フレームを書き出す。

    include_last=False のとき終端 (t=1.0) は書かず、次ペアの先頭に任せる。
    """
    morpher.prepare(img1, img2)
    last = transition_frames if include_last else transition_frames - 1
    for i in range(0, last + 1):
        raw_t = i / transition_frames
        t = easing(raw_t)
        writer.write(morpher.frame(img1, img2, t))


def build_video(
    inputs: List[str],
    output: str,
    method: str = "flow",
    fps: float = 30.0,
    transition_seconds: float = 1.0,
    hold_seconds: float = 0.5,
    size: Optional[Tuple[int, int]] = None,
    easing: str = "ease_in_out",
    loop: bool = False,
    aspect: Optional[str] = None,
    fill: str = "blur",
    morpher_kwargs: Optional[dict] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> str:
    """画像列をモーフィング動画に変換して output に保存する。

    Parameters
    ----------
    inputs:
        正規化済みの画像パス一覧 (2 枚以上)。
    method:
        ``crossfade`` / ``flow`` / ``feature`` のいずれか。
    transition_seconds:
        1 つの遷移にかける秒数。
    hold_seconds:
        各キーフレームを静止表示する秒数。
    loop:
        True で末尾から先頭へ戻る遷移を追加し、ループ再生向きにする。
    """
    if len(inputs) < 2:
        raise ValueError("モーフィングには 2 枚以上の画像が必要です。")

    morpher = get_morpher(method, **(morpher_kwargs or {}))
    ease = get_easing(easing)
    say = progress or (lambda _msg: None)

    images = load_and_normalize(inputs, size)
    h, w = images[0].shape[:2]
    out_size = (w, h)

    # 書き出しアスペクト比（SNS / プレゼン用途）。指定時はフレームをレターボックス。
    transform = None
    if aspect:
        ow, oh = compute_aspect_size(w, h, aspect)
        out_size = (ow, oh)
        transform = lambda f: fit_frame(f, ow, oh, fill)  # noqa: E731

    transition_frames = max(1, int(round(transition_seconds * fps)))
    hold_frames = max(0, int(round(hold_seconds * fps)))

    sequence = list(images)
    if loop:
        sequence = sequence + [images[0]]

    with VideoWriter(output, fps, out_size, transform=transform) as writer:
        for idx in range(len(sequence)):
            img = sequence[idx]
            # キーフレームの静止表示
            for _ in range(hold_frames):
                writer.write(img)
            # 次の画像への遷移 (最後のフレームは次キーフレームの hold が担うので書かない)
            if idx < len(sequence) - 1:
                nxt = sequence[idx + 1]
                say(f"[{idx + 1}/{len(sequence) - 1}] {method} モーフィング中...")
                _morph_pair(
                    writer, morpher, img, nxt, transition_frames, ease, include_last=False
                )

    say(f"完了: {writer.path} ({writer.count} フレーム, {out_size[0]}x{out_size[1]}, {fps}fps)")
    return output
