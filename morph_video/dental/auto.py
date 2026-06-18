"""審美的主訴のオート判定（OpenCV ヒューリスティック）。

学習済みモデルや重い依存を使わず、顔・口元の領域推定と色/明るさ/対称性の
解析から主訴の「候補」を信頼度つきで提示する補助機能。あくまで術者確認を
前提とした参考であり、確定診断ではない。

仕組みの概要:
- 顔を検出できれば下顔面中央を口元 ROI とする。検出できない場合は口腔内
  接写写真とみなし画像中央領域を対象にする。
- ROI 内で「歯」（高明度・低彩度）と「歯肉」（赤系）を色で大まかに分離。
- 歯の黄色味 → 変色、歯肉/歯の面積比 → ガミースマイル、暗い金属色 → 銀歯、
  歯領域の左右非対称 → 正中のずれ、歯の暗い間隙 → 欠損/空隙、の候補を算出。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class AutoFinding:
    code: str
    confidence: float  # 0..1（補助的指標）
    metric: Dict[str, float] = field(default_factory=dict)
    note: str = ""


def _load_face_cascade() -> Optional[cv2.CascadeClassifier]:
    path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    clf = cv2.CascadeClassifier(path)
    return None if clf.empty() else clf


def _find_mouth_roi(img: np.ndarray) -> Tuple[Tuple[int, int, int, int], bool]:
    """口元 ROI (x, y, w, h) と「顔が見つかったか」を返す。

    顔が見つかれば下顔面中央。見つからなければ画像中央領域（口腔内接写を想定）。
    """
    h, w = img.shape[:2]
    cascade = _load_face_cascade()
    if cascade is not None:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
        if len(faces) > 0:
            fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            # 下顔面中央（口元）を切り出す
            mx = fx + int(fw * 0.18)
            mw = int(fw * 0.64)
            my = fy + int(fh * 0.58)
            mh = int(fh * 0.34)
            mx = max(0, mx); my = max(0, my)
            mw = min(mw, w - mx); mh = min(mh, h - my)
            if mw > 10 and mh > 10:
                return (mx, my, mw, mh), True
    # フォールバック: 画像中央 80%
    mx, my = int(w * 0.1), int(h * 0.1)
    return (mx, my, int(w * 0.8), int(h * 0.8)), False


def _masks(roi_bgr: np.ndarray):
    """ROI から歯マスク・歯肉マスク・暗部マスクを作る。"""
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    # 歯: 明るく彩度が低い
    teeth = ((V > 110) & (S < 90)).astype(np.uint8)
    teeth = cv2.morphologyEx(teeth, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # 歯肉: 赤〜ピンク系（Hue が赤付近）でそこそこ彩度がある
    red = (((H < 12) | (H > 168)) & (S > 60) & (V > 60)).astype(np.uint8)
    gum = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    # 暗部: 金属/影/欠損の手がかり（低明度）
    dark = ((V < 70)).astype(np.uint8)

    return teeth, gum, dark


def _yellowness(roi_bgr: np.ndarray, teeth: np.ndarray) -> float:
    """歯領域の黄色味を LAB の b* から推定し 0..1 に正規化。"""
    if teeth.sum() < 30:
        return 0.0
    lab = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2LAB)
    b = lab[..., 2].astype(np.float32)  # 128 中心、>128 で黄方向
    vals = b[teeth.astype(bool)]
    mean_b = float(np.mean(vals))
    # b*=128 で 0、b*=160 程度で 1 になるようスケール
    return float(np.clip((mean_b - 128.0) / 32.0, 0.0, 1.0))


def detect_complaints(
    image: np.ndarray, min_confidence: float = 0.35
) -> List[AutoFinding]:
    """画像から審美的主訴の候補を信頼度つきで返す。

    Parameters
    ----------
    image:
        BGR uint8 画像（術前写真を推奨。正面の笑顔または口腔内接写）。
    min_confidence:
        この値未満の候補は返さない。
    """
    if image is None or image.size == 0:
        return []

    (rx, ry, rw, rh), face_found = _find_mouth_roi(image)
    roi = image[ry:ry + rh, rx:rx + rw]
    if roi.size == 0:
        return []

    teeth, gum, dark = _masks(roi)
    area = float(rw * rh)
    teeth_area = float(teeth.sum())
    gum_area = float(gum.sum())

    findings: List[AutoFinding] = []

    # --- 変色（歯の黄色味） ---
    yellow = _yellowness(roi, teeth)
    if teeth_area > area * 0.04:
        conf = yellow
        findings.append(
            AutoFinding(
                "discoloration",
                round(conf, 2),
                {"yellowness": round(yellow, 2), "teeth_ratio": round(teeth_area / area, 3)},
                "歯領域の黄色味から推定。照明・ホワイトバランスの影響を受けるため要確認。",
            )
        )

    # --- ガミースマイル（歯肉露出比） ---
    if teeth_area > 30:
        gum_ratio = gum_area / max(teeth_area, 1.0)
        # 歯肉が歯に対して相対的に多いほど高スコア（0.6 で頭打ち）
        conf = float(np.clip(gum_ratio / 0.6, 0.0, 1.0))
        findings.append(
            AutoFinding(
                "gummy_smile",
                round(conf, 2),
                {"gum_teeth_ratio": round(gum_ratio, 2)},
                "歯肉と歯の面積比から推定。笑顔の写真でないと過小評価になりやすい。",
            )
        )

    # --- 銀歯/金属色（歯列内の低彩度・低明度のまとまり） ---
    if teeth_area > 30:
        # 歯の近傍にある暗部の割合
        teeth_dil = cv2.dilate(teeth, np.ones((9, 9), np.uint8))
        metalish = ((dark > 0) & (teeth_dil > 0)).sum()
        metal_ratio = metalish / max(teeth_area, 1.0)
        conf = float(np.clip(metal_ratio / 0.25, 0.0, 1.0))
        findings.append(
            AutoFinding(
                "metal_restoration",
                round(conf, 2),
                {"dark_in_arch_ratio": round(metal_ratio, 3)},
                "歯列内の暗い領域から推定。う蝕・影・口腔内陰影と区別できないため要確認。",
            )
        )

    # --- 正中・左右非対称（歯マスク重心の左右ずれ） ---
    if teeth_area > area * 0.05:
        ys, xs = np.nonzero(teeth)
        cx = float(np.mean(xs))
        offset = abs(cx - rw / 2.0) / (rw / 2.0)  # 0=中央, 1=端
        conf = float(np.clip(offset / 0.25, 0.0, 1.0))
        findings.append(
            AutoFinding(
                "midline_deviation",
                round(conf, 2),
                {"center_offset": round(offset, 3)},
                "歯列重心の左右ずれから推定。顔の向き・トリミングの影響を受ける。",
            )
        )

    # 信頼度でフィルタし降順に
    findings = [f for f in findings if f.confidence >= min_confidence]
    findings.sort(key=lambda f: f.confidence, reverse=True)

    for f in findings:
        f.metric["roi"] = 1.0 if face_found else 0.0  # 1=顔検出, 0=接写フォールバック
    return findings
