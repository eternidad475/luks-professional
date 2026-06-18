"""画像の読み込み・リサイズと動画書き出しのユーティリティ。"""

from __future__ import annotations

import glob
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

# 一般的な画像拡張子
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


def expand_inputs(paths: List[str]) -> List[str]:
    """与えられたパス／ディレクトリ／グロブを画像ファイルの一覧に展開する。

    - ディレクトリが渡されたら、その中の画像を名前順で取り込む
    - グロブ (``*.png`` 等) を展開する
    - それ以外はファイルとしてそのまま採用する
    """
    result: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            entries = sorted(
                os.path.join(p, f)
                for f in os.listdir(p)
                if f.lower().endswith(_IMAGE_EXTS)
            )
            result.extend(entries)
        elif any(ch in p for ch in "*?[") :
            result.extend(sorted(glob.glob(p)))
        else:
            result.append(p)
    return result


def load_image(path: str) -> np.ndarray:
    """BGR の uint8 画像として読み込む。失敗時は例外。"""
    # 日本語パス等にも対応するため imdecode 経由で読み込む
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"画像を読み込めませんでした: {path}")
    return img


def _fit_size(
    images: List[np.ndarray], size: Optional[Tuple[int, int]]
) -> Tuple[int, int]:
    if size is not None:
        return size
    # 指定が無ければ先頭画像のサイズに揃える
    h, w = images[0].shape[:2]
    return (w, h)


def load_and_normalize(
    paths: List[str], size: Optional[Tuple[int, int]] = None
) -> List[np.ndarray]:
    """全画像を同じ解像度・3 チャンネルに揃えて読み込む。

    size が None の場合は先頭画像の解像度に合わせる。
    """
    if not paths:
        raise ValueError("入力画像がありません。")

    images = [load_image(p) for p in paths]
    target_w, target_h = _fit_size(images, size)

    normalized: List[np.ndarray] = []
    for img in images:
        if img.shape[1] != target_w or img.shape[0] != target_h:
            img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_AREA)
        normalized.append(np.ascontiguousarray(img))
    return normalized


# 書き出しアスペクト比（SNS / プレゼン用途）
ASPECTS = {
    "9:16": (9, 16),
    "4:5": (4, 5),
    "1:1": (1, 1),
    "16:9": (16, 9),
}


def _even(n: int) -> int:
    n = int(round(n))
    return n if n % 2 == 0 else n + 1


def compute_aspect_size(src_w: int, src_h: int, aspect: str) -> Tuple[int, int]:
    """元画像がちょうど収まる、指定アスペクト比のキャンバスサイズを返す。"""
    aw, ah = ASPECTS[aspect]
    ratio = aw / ah
    out_w, out_h = src_w, round(src_w / ratio)
    if out_h < src_h:  # 高さが足りなければ高さ基準で取り直す
        out_h, out_w = src_h, round(src_h * ratio)
    return _even(out_w), _even(out_h)


def _hex_bgr(h: str) -> Tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))  # BGR


def _gradient(out_w: int, out_h: int, colors) -> np.ndarray:
    """2 色の対角線形グラデーション (BGR)。"""
    c1 = np.array(_hex_bgr(colors[0]), np.float32)
    c2 = np.array(_hex_bgr(colors[1] if len(colors) > 1 else colors[0]), np.float32)
    yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
    t = (xx / max(out_w - 1, 1) + yy / max(out_h - 1, 1)) / 2.0
    canvas = c1[None, None, :] * (1 - t[..., None]) + c2[None, None, :] * t[..., None]
    return canvas.astype(np.uint8)


def fit_frame(
    frame: np.ndarray, out_w: int, out_h: int, fill: str = "blur", colors=None
) -> np.ndarray:
    """frame を (out_w, out_h) のキャンバスにレターボックス配置する。

    fill: "blur"（拡大ぼかし）/ "white" / "black" / "gradient"（colors=(hexA,hexB)）。
    """
    fh, fw = frame.shape[:2]
    scale = min(out_w / fw, out_h / fh)
    nw, nh = max(1, int(round(fw * scale))), max(1, int(round(fh * scale)))
    resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)

    if fill == "blur":
        cov = max(out_w / fw, out_h / fh)
        cw, ch = max(1, int(round(fw * cov))), max(1, int(round(fh * cov)))
        bg = cv2.resize(frame, (cw, ch), interpolation=cv2.INTER_LINEAR)
        x0, y0 = (cw - out_w) // 2, (ch - out_h) // 2
        bg = bg[y0:y0 + out_h, x0:x0 + out_w]
        k = max(9, (min(out_w, out_h) // 12) | 1)  # 奇数カーネル
        canvas = cv2.GaussianBlur(bg, (k, k), 0)
        canvas = (canvas.astype(np.float32) * 0.7).astype(np.uint8)  # やや暗くして主役を立てる
    elif fill == "gradient":
        canvas = _gradient(out_w, out_h, colors or ("#7c5cff", "#ff9fd6"))
    else:
        color = (255, 255, 255) if fill == "white" else (0, 0, 0)
        canvas = np.full((out_h, out_w, 3), color, np.uint8)

    ox, oy = (out_w - nw) // 2, (out_h - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = resized
    return canvas


class VideoWriter:
    """cv2.VideoWriter の薄いラッパー (with 構文対応)。

    transform を渡すと各フレームに適用してから書き込む（アスペクト比変換等）。
    """

    def __init__(self, path: str, fps: float, size: Tuple[int, int],
                 fourcc: str = "mp4v", transform=None):
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        code = cv2.VideoWriter_fourcc(*fourcc)
        self._writer = cv2.VideoWriter(path, code, fps, size)
        if not self._writer.isOpened():
            raise RuntimeError(
                f"動画ファイルを開けませんでした: {path} (fourcc={fourcc})"
            )
        self.path = path
        self.size = size
        self.transform = transform
        self.count = 0


    def write(self, frame: np.ndarray) -> None:
        if self.transform is not None:
            frame = self.transform(frame)
        if (frame.shape[1], frame.shape[0]) != self.size:
            frame = cv2.resize(frame, self.size)
        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)
        self._writer.write(frame)
        self.count += 1

    def close(self) -> None:
        self._writer.release()

    def __enter__(self) -> "VideoWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
