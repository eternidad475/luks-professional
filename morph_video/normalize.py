"""共通の画像正規化・コアランドマーク・二層メッシュの基盤。

facial（顔貌）と focus（口元）で **別々の幾何パイプラインを持たせず**、共通の
座標系・共通ランドマーク・共通メッシュを使うための土台。外部の機械学習モデルに
依存せず numpy / opencv のみで動作する。

設計:
  * ``ManualAdjust``  … 手動ガイド（正中/スマイル/切縁/歯頸 + 口中心/ROI）を
                        正規化座標(0..1)で保持。既存の manual alignment UI の値。
  * ``CoreLandmarks`` … facial/focus 共通のコアランドマーク（正規化座標）。
                        手動ガイド（+簡易オート）から導出する。
  * ``normalize_image`` … 向き補正済み画像を長辺 ``long_side`` に標準化。
  * ``auto_mouth_roi``  … Haar で顔検出→口ROIを推定（失敗時は下中央デフォルト）。
  * ``two_layer_mesh``  … coarse global mesh + denser mouth ROI submesh の点群。
                        focus は ROI を強調、facial は全体の自然さを優先するが、
                        **基盤（点群・座標系）は共通**。

注意: 本モジュールの出力は記録・患者説明の補助であり、診断・計測を目的とした
医療機器レベルの精度を保証するものではない。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
# 手動ガイド（既存 manual alignment UI の値）＝共通ランドマークの補正値
# --------------------------------------------------------------------------- #
@dataclass
class ManualAdjust:
    """手動ガイド値（すべて正規化座標 0..1 / 正規化画像基準）。

    既存 UI のガイド（正中の縦線、スマイル/切縁/歯頸の横線）に対応。未指定なら
    臨床写真の一般的な既定値を使う。focus 用に口中心・ROI 半径も持つ。
    """

    midline_x: float = 0.50    # 正中（dental midline, 縦線）
    smile_y: float = 0.62      # スマイルライン（横線）
    incisal_y: float = 0.66    # 切縁ライン（横線）
    gingival_y: float = 0.55   # 歯頸ライン（横線）
    mouth_cx: float = 0.50     # 口中心 x（focus ROI 用）
    mouth_cy: float = 0.64     # 口中心 y
    roi_scale: float = 1.0     # ROI 半径のスケール（1.0=既定）

    @classmethod
    def from_dict(cls, d: Optional[Dict]) -> "ManualAdjust":
        d = d or {}
        base = cls()
        for k in base.__dataclass_fields__:
            if k in d and d[k] is not None:
                try:
                    setattr(base, k, float(d[k]))
                except (TypeError, ValueError):
                    pass
        base.clamp()
        return base

    def clamp(self) -> "ManualAdjust":
        for k in ("midline_x", "smile_y", "incisal_y", "gingival_y", "mouth_cx", "mouth_cy"):
            setattr(self, k, float(min(1.0, max(0.0, getattr(self, k)))))
        self.roi_scale = float(min(2.5, max(0.4, self.roi_scale)))
        return self

    def to_dict(self) -> Dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# facial / focus 共通のコアランドマーク
# --------------------------------------------------------------------------- #
@dataclass
class CoreLandmarks:
    """共通コアランドマーク（正規化座標 0..1）。

    facial は全体の自然さ、focus は口元強調に使うが、**同一の座標系・同一の
    ランドマーク集合**を共有する。値は手動ガイド or 簡易オートから導出。
    """

    face_center: Tuple[float, float]
    eyes_ref_y: float
    mouth_left: Tuple[float, float]
    mouth_right: Tuple[float, float]
    upper_lip: List[Tuple[float, float]]
    lower_lip: List[Tuple[float, float]]
    smile_line: float
    dental_midline: float
    incisal_line: float
    gingival_line: float
    anterior_anchors: List[Tuple[float, float]]

    def to_dict(self) -> Dict:
        return asdict(self)


def normalize_image(img: np.ndarray, long_side: int = 1400) -> Tuple[np.ndarray, float]:
    """画像を長辺 ``long_side`` に標準化（縮小のみ・拡大はしない）。

    返り値 ``(normalized_img, scale)``。EXIF 回転は呼び出し側で補正済みを想定
    （ブラウザの canvas 経由 dataURL は回転補正済み）。
    """
    h, w = img.shape[:2]
    if max(h, w) <= 0:
        return np.ascontiguousarray(img), 1.0
    scale = long_side / float(max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))),
                         interpolation=cv2.INTER_AREA)
    else:
        scale = 1.0
    return np.ascontiguousarray(img), scale


_FACE_CASCADE: Optional[cv2.CascadeClassifier] = None


def _face_cascade() -> Optional[cv2.CascadeClassifier]:
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        try:
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cc = cv2.CascadeClassifier(path)
            _FACE_CASCADE = cc if not cc.empty() else None
        except Exception:
            _FACE_CASCADE = None
    return _FACE_CASCADE


def auto_mouth_roi(img: np.ndarray) -> Tuple[float, float, float]:
    """口元 ROI を推定して (cx, cy, r) を正規化座標で返す。

    Haar 顔検出に成功したら顔の下寄り中央を口とみなす。失敗時は臨床スマイル写真の
    一般的な位置（下中央やや上）を既定値として返す。
    """
    default = (0.50, 0.64, 0.26)
    cc = _face_cascade()
    if cc is None:
        return default
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        H, W = gray.shape[:2]
        faces = cc.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5,
                                    minSize=(max(48, W // 12), max(48, H // 12)))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
            cx = (x + w / 2.0) / W
            cy = (y + h * 0.78) / H            # 口は顔の下 ~3/4 付近
            r = (w * 0.42) / W
            return (float(cx), float(cy), float(max(0.12, min(0.45, r))))
    except Exception:
        pass
    return default


def core_landmarks(shape: Tuple[int, int], manual: ManualAdjust) -> CoreLandmarks:
    """手動ガイド（+既定値）から共通コアランドマークを構築する。

    ``shape`` は (h, w)。座標はすべて 0..1 正規化。口角は口中心±ROI半径から、
    上下唇輪郭は口角と切縁/スマイルラインから素直に導く（説明用の近似）。
    """
    m = manual
    cx = m.mouth_cx
    half = 0.13 * m.roi_scale                       # 口角までの半幅（正規化）
    left = (max(0.0, cx - half), m.smile_y)
    right = (min(1.0, cx + half), m.smile_y)
    upper = [left, (cx, m.gingival_y), right]        # 上唇/歯頸側
    lower = [left, (cx, m.incisal_y), right]         # 下唇/切縁側
    anchors = [
        (cx, m.incisal_y),                           # 正中切縁
        (max(0.0, cx - half * 0.5), m.incisal_y),    # 側切歯付近
        (min(1.0, cx + half * 0.5), m.incisal_y),
    ]
    return CoreLandmarks(
        face_center=(m.midline_x, (m.smile_y + m.gingival_y) / 2.0),
        eyes_ref_y=max(0.0, m.gingival_y - 0.32),
        mouth_left=left,
        mouth_right=right,
        upper_lip=upper,
        lower_lip=lower,
        smile_line=m.smile_y,
        dental_midline=m.midline_x,
        incisal_line=m.incisal_y,
        gingival_line=m.gingival_y,
        anterior_anchors=anchors,
    )


def _grid_points(x0: float, y0: float, x1: float, y1: float, nx: int, ny: int) -> np.ndarray:
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    gx, gy = np.meshgrid(xs, ys)
    return np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float32)


def two_layer_mesh(
    shape: Tuple[int, int],
    landmarks: CoreLandmarks,
    roi: Optional[Tuple[float, float, float]] = None,
    coarse: Tuple[int, int] = (7, 9),
    dense: Tuple[int, int] = (9, 9),
) -> Dict[str, np.ndarray]:
    """coarse global mesh + denser mouth ROI submesh の点群（ピクセル座標）を返す。

    どちらも同じ画像座標系上に構築する共通基盤。focus は ``roi`` サブメッシュを
    強調して使い、facial は ``global`` メッシュ（全体の自然さ）を主に使う。

    返り値: ``{"global": (N,2) float32, "roi": (M,2) float32, "roi_box": (x0,y0,x1,y1)}``。
    """
    h, w = shape[:2]
    if roi is None:
        roi = (landmarks.dental_midline, landmarks.smile_line, 0.26)
    cx, cy, r = roi
    # global: 画像全体の粗グリッド（四隅を含む）
    g = _grid_points(0, 0, w - 1, h - 1, coarse[0], coarse[1])
    # roi: 口元まわりの密グリッド
    x0 = max(0.0, (cx - r * 1.4)) * (w - 1)
    x1 = min(1.0, (cx + r * 1.4)) * (w - 1)
    y0 = max(0.0, (cy - r * 1.1)) * (h - 1)
    y1 = min(1.0, (cy + r * 1.1)) * (h - 1)
    roi_pts = _grid_points(x0, y0, x1, y1, dense[0], dense[1])
    return {
        "global": g,
        "roi": roi_pts,
        "roi_box": np.array([x0, y0, x1, y1], dtype=np.float32),
    }


def align_to_canonical(
    img: np.ndarray, manual: ManualAdjust,
    canon_mid: float = 0.5, canon_smile: float = 0.62,
) -> Tuple[np.ndarray, np.ndarray]:
    """手動ガイド（正中・スマイル）を基準に、画像を共通の正準位置へ平行移動する。

    正中 x とスマイル y を canonical 位置へ寄せる控えめな平行移動のみ（過補正で
    症例が破綻しないよう回転・強い拡大縮小はしない）。返り値 ``(img, 2x3 matrix)``。
    facial/focus の両方でこの共通正準座標系を使うことで、Preview と MP4 の見えを揃える。
    """
    h, w = img.shape[:2]
    dx = (canon_mid - manual.midline_x) * w
    dy = (canon_smile - manual.smile_y) * h
    # 端が大きく欠けないよう移動量を画像の 12% までに制限
    dx = float(np.clip(dx, -0.12 * w, 0.12 * w))
    dy = float(np.clip(dy, -0.12 * h, 0.12 * h))
    mat = np.float32([[1, 0, dx], [0, 1, dy]])
    out = cv2.warpAffine(img, mat, (w, h), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_REFLECT_101)
    return np.ascontiguousarray(out), mat


def normalize_case(
    images: List[np.ndarray],
    manuals: Optional[List[Optional[Dict]]] = None,
    long_side: int = 1400,
    align: bool = False,
) -> Dict[str, object]:
    """症例（複数画像）を共通座標系へ正規化し、共通ランドマーク・メッシュを返す。

    すべての画像を同一解像度（先頭画像基準）に揃え、各画像のコアランドマークと
    二層メッシュ、共通の口元 ROI を計算する。これが facial/focus 共通の基盤となる。

    返り値 dict:
      ``images``     … 正規化済み画像 list
      ``landmarks``  … 各画像の CoreLandmarks list
      ``roi``        … 症例共通の口元 ROI (cx,cy,r)（先頭画像から推定）
      ``meshes``     … 各画像の two_layer_mesh list
    """
    if not images:
        raise ValueError("入力画像がありません。")
    manuals = manuals or [None] * len(images)

    norm = [normalize_image(im, long_side)[0] for im in images]
    # 全画像を先頭サイズへ統一（共通座標系）
    th, tw = norm[0].shape[:2]
    for i in range(len(norm)):
        if norm[i].shape[1] != tw or norm[i].shape[0] != th:
            norm[i] = cv2.resize(norm[i], (tw, th), interpolation=cv2.INTER_AREA)

    adjusts = [ManualAdjust.from_dict(manuals[i] if i < len(manuals) else None)
               for i in range(len(norm))]
    if align:
        for i in range(len(norm)):
            norm[i], _ = align_to_canonical(norm[i], adjusts[i])

    # 症例共通 ROI: 先頭画像のオート推定 or 手動値
    a0 = adjusts[0]
    if manuals and manuals[0]:
        roi = (a0.mouth_cx, a0.mouth_cy, 0.26 * a0.roi_scale)
    else:
        roi = auto_mouth_roi(norm[0])

    lms = [core_landmarks((th, tw), adjusts[i]) for i in range(len(norm))]
    meshes = [two_layer_mesh((th, tw), lms[i], roi) for i in range(len(norm))]
    return {"images": norm, "landmarks": lms, "roi": roi, "meshes": meshes,
            "size": (tw, th)}
