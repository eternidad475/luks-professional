"""複数画像を順番にモーフィングでつないで 1 本の動画にするパイプライン。"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np

from .easing import get_easing
from .io_utils import VideoWriter, compute_aspect_size, fit_frame, load_and_normalize
from .morphers import Morpher, get_morpher


def _morph_pair(
    emit: Callable[[np.ndarray, int], None],
    morpher: Morpher,
    img1: np.ndarray,
    img2: np.ndarray,
    transition_frames: int,
    easing: Callable[[float], float],
    include_last: bool,
    idx1: int = 0,
    idx2: int = 0,
) -> None:
    """img1 -> img2 の遷移フレームを emit(frame, keyframe_idx) で書き出す。

    include_last=False のとき終端 (t=1.0) は書かず、次ペアの先頭に任せる。
    """
    morpher.prepare(img1, img2)
    last = transition_frames if include_last else transition_frames - 1
    for i in range(0, last + 1):
        raw_t = i / transition_frames
        t = easing(raw_t)
        emit(morpher.frame(img1, img2, t), idx1 if raw_t < 0.5 else idx2)


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
    fill_colors: Optional[Tuple[str, str]] = None,
    labels: Optional[List[str]] = None,
    decorator: Optional[Callable[[np.ndarray, str, int, int], np.ndarray]] = None,
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
    n = len(images)

    # 書き出しアスペクト比（SNS / プレゼン用途）。指定時はフレームをレターボックス。
    ow, oh = w, h
    if aspect:
        ow, oh = compute_aspect_size(w, h, aspect)
        out_size = (ow, oh)

    labels = list(labels) if labels else [""] * n
    if len(labels) < n:
        labels += [""] * (n - len(labels))

    transition_frames = max(1, int(round(transition_seconds * fps)))
    hold_frames = max(0, int(round(hold_seconds * fps)))

    sequence = list(images)
    seq_idx = list(range(n))
    if loop:
        sequence = sequence + [images[0]]
        seq_idx = seq_idx + [0]

    with VideoWriter(output, fps, out_size) as writer:
        # 各フレーム共通の整形：アスペクト変換 → テンプレート/ラベル装飾
        def emit(frame: np.ndarray, kidx: int) -> None:
            f = frame
            if aspect:
                f = fit_frame(f, ow, oh, fill, fill_colors)
            if decorator is not None:
                f = decorator(f, labels[kidx % n], kidx % n, n)
            writer.write(f)

        for pos in range(len(sequence)):
            kidx = seq_idx[pos]
            for _ in range(hold_frames):
                emit(sequence[pos], kidx)
            if pos < len(sequence) - 1:
                say(f"[{pos + 1}/{len(sequence) - 1}] {method} モーフィング中...")
                _morph_pair(
                    emit, morpher, sequence[pos], sequence[pos + 1],
                    transition_frames, ease, include_last=False,
                    idx1=kidx, idx2=seq_idx[pos + 1],
                )

    say(f"完了: {writer.path} ({writer.count} フレーム, {out_size[0]}x{out_size[1]}, {fps}fps)")
    return output
