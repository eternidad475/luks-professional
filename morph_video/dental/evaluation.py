"""マクロ評価（顔貌とスマイル）／ミクロ評価（歯と歯肉）。

審美歯科の評価軸を OpenCV ヒューリスティックで定量化する補助機能。学習済み
モデルは使わない。すべて照明・撮影条件・トリミングの影響を受けるため、結果は
あくまで「参考値」であり術者の確認を要する。

- マクロ (kind="macro"): 正中線の一致 / スマイルライン / スマイル幅 / 歯の露出量
- ミクロ (kind="micro"): 黄金比 / 色と透明感 / 形態と質感 / 歯肉のライン
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .auto import _find_mouth_roi, _load_face_cascade, _masks

GOOD, CHECK, REF, NA = "良好", "要確認", "参考", "判定不可"


@dataclass
class Metric:
    key: str
    label: str
    value: str  # 表示用（数値や記述）
    status: str  # GOOD / CHECK / REF / NA
    score: Optional[float] = None  # 0..1（高いほど良い）。記述系は None
    note: str = ""


@dataclass
class Evaluation:
    kind: str  # "macro" / "micro"
    title: str
    metrics: List[Metric] = field(default_factory=list)
    derived_complaints: List[str] = field(default_factory=list)  # 評価から導く主訴候補


# --------------------------------------------------------------------------- #
# 共通ユーティリティ
# --------------------------------------------------------------------------- #
def _status_from_score(score: float, good: float = 0.7, check: float = 0.4) -> str:
    if score >= good:
        return GOOD
    if score >= check:
        return CHECK
    return CHECK


def _detect_face(img: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    clf = _load_face_cascade()
    if clf is None:
        return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = clf.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    return tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3]))


def _eye_centers(img: np.ndarray, face: Tuple[int, int, int, int]) -> Optional[Tuple[float, float]]:
    """顔上半分から両目を検出し、左右の目の中心 x を返す。"""
    path = os.path.join(cv2.data.haarcascades, "haarcascade_eye.xml")
    clf = cv2.CascadeClassifier(path)
    if clf.empty():
        return None
    fx, fy, fw, fh = face
    upper = cv2.cvtColor(img[fy:fy + fh // 2, fx:fx + fw], cv2.COLOR_BGR2GRAY)
    eyes = clf.detectMultiScale(upper, 1.1, 5, minSize=(20, 20))
    if len(eyes) < 2:
        return None
    eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
    centers = sorted(fx + e[0] + e[2] / 2.0 for e in eyes)
    return centers[0], centers[1]


def _facial_midline_x(img: np.ndarray, face: Optional[Tuple[int, int, int, int]]) -> Optional[float]:
    if face is None:
        return None
    eyes = _eye_centers(img, face)
    if eyes is not None:
        return (eyes[0] + eyes[1]) / 2.0
    fx, _, fw, _ = face
    return fx + fw / 2.0


def _teeth_band(teeth: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """歯マスクの外接矩形 (x, y, w, h)。"""
    ys, xs = np.nonzero(teeth)
    if xs.size < 30:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


def _tooth_widths(teeth: np.ndarray) -> List[Tuple[float, float]]:
    """歯マスクの列方向プロファイルから個々の歯の (中心x, 幅) を左→右で返す。"""
    band = _teeth_band(teeth)
    if band is None:
        return []
    x0, y0, w, h = band
    sub = teeth[y0:y0 + h, x0:x0 + w]
    col = sub.sum(axis=0).astype(np.float32)
    if col.max() <= 0:
        return []
    thr = col.max() * 0.25
    on = col >= thr
    widths: List[Tuple[float, float]] = []
    start = None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            widths.append((x0 + (start + i - 1) / 2.0, float(i - start)))
            start = None
    if start is not None:
        widths.append((x0 + (start + len(on) - 1) / 2.0, float(len(on) - start)))
    # ノイズ除去: 平均幅の 25% 未満は捨てる
    if widths:
        mean_w = float(np.mean([wd for _, wd in widths]))
        widths = [(cx, wd) for cx, wd in widths if wd >= mean_w * 0.25]
    return widths


# --------------------------------------------------------------------------- #
# マクロ評価（顔貌とスマイル）
# --------------------------------------------------------------------------- #
def evaluate_macro(img: np.ndarray) -> Evaluation:
    ev = Evaluation("macro", "マクロ評価（顔貌とスマイル）")
    if img is None or img.size == 0:
        return ev

    face = _detect_face(img)
    (rx, ry, rw, rh), _ = _find_mouth_roi(img)
    roi = img[ry:ry + rh, rx:rx + rw]
    teeth, gum, _ = _masks(roi)
    band = _teeth_band(teeth)
    face_w = float(face[2]) if face else float(img.shape[1])

    # 1) 正中線の一致
    facial_mid = _facial_midline_x(img, face)
    if facial_mid is not None and band is not None:
        ys, xs = np.nonzero(teeth)
        dental_mid = rx + float(np.mean(xs))
        offset = abs(dental_mid - facial_mid) / max(face_w, 1.0)
        score = float(np.clip(1.0 - offset / 0.06, 0.0, 1.0))
        ev.metrics.append(
            Metric(
                "midline", "正中線の一致",
                f"顔正中とのずれ ≈ 顔幅の {offset * 100:.1f}%",
                _status_from_score(score), round(score, 2),
                "顔の中心線と前歯正中のラインの一致度。顔の向きの影響を受ける。",
            )
        )
        if offset > 0.03:
            ev.derived_complaints.append("midline_deviation")
    else:
        ev.metrics.append(Metric("midline", "正中線の一致", "—", NA, None,
                                 "顔・両目または歯列を検出できず判定不可。"))

    # 2) スマイルライン（上顎切縁ラインの湾曲と対称性）
    if band is not None:
        x0, y0, w, h = band
        sub = teeth[y0:y0 + h, x0:x0 + w]
        edge_y = []
        xs_n = []
        for c in range(w):
            col = np.nonzero(sub[:, c])[0]
            if col.size:
                edge_y.append(float(col.max()))  # 列ごとの切縁（最下点）
                xs_n.append((c / max(w - 1, 1)) * 2 - 1)  # -1..1
        if len(edge_y) >= 5:
            a, b, _c = np.polyfit(xs_n, edge_y, 2)
            # a>0: 中央が浅く端が深い=コンケーブ, a<0: 中央が下がる=スマイルに調和的
            consonant = a < 0
            symmetry = float(np.clip(1.0 - abs(b) / (h * 0.5 + 1e-6), 0.0, 1.0))
            shape = "下唇カーブに調和（コンソナント）" if consonant else "フラット〜逆カーブ傾向"
            score = symmetry * (0.8 if consonant else 0.5)
            ev.metrics.append(
                Metric(
                    "smile_line", "スマイルライン",
                    f"{shape} / 左右対称性 {symmetry * 100:.0f}%",
                    _status_from_score(score), round(score, 2),
                    "切縁を結ぶラインの湾曲方向と左右対称性。笑顔の正面写真を推奨。",
                )
            )
        else:
            ev.metrics.append(Metric("smile_line", "スマイルライン", "—", NA, None,
                                     "切縁ラインを十分に抽出できず判定不可。"))
    else:
        ev.metrics.append(Metric("smile_line", "スマイルライン", "—", NA, None,
                                 "歯列を検出できず判定不可。"))

    # 3) スマイル幅（口角間に対する歯列幅＝バッカルコリドー）
    if band is not None:
        teeth_w = band[2]
        ratio = teeth_w / max(rw, 1)  # 口元 ROI 幅に対する歯列幅
        corridor = float(np.clip(1.0 - ratio, 0.0, 1.0))
        # コリドーは広すぎても狭すぎても不自然。10〜25% を目安に
        score = float(np.clip(1.0 - abs(corridor - 0.17) / 0.2, 0.0, 1.0))
        ev.metrics.append(
            Metric(
                "smile_width", "スマイル幅 / バッカルコリドー",
                f"歯列幅は口元幅の {ratio * 100:.0f}% / コリドー {corridor * 100:.0f}%",
                _status_from_score(score), round(score, 2),
                "口角から口角に対する歯の見える範囲のバランス。広いコリドーは口角の暗がりが目立つ。",
            )
        )
    else:
        ev.metrics.append(Metric("smile_width", "スマイル幅 / バッカルコリドー", "—", NA, None,
                                 "歯列を検出できず判定不可。"))

    # 4) 歯の露出量（口元開口に対する歯の高さ）+ ガミー傾向
    if band is not None and teeth.sum() > 0:
        teeth_h = band[3]
        display = teeth_h / max(rh, 1)
        gum_ratio = float(gum.sum()) / max(float(teeth.sum()), 1.0)
        gummy = gum_ratio > 0.6
        ev.metrics.append(
            Metric(
                "tooth_display", "歯の露出量",
                f"口元高に対し上顎歯の高さ {display * 100:.0f}% / 歯肉比 {gum_ratio:.2f}"
                + ("（歯肉露出やや多）" if gummy else ""),
                REF, None,
                "笑った際の上顎前歯の見える量。安静時/スマイル時で評価が変わる。",
            )
        )
        if gummy:
            ev.derived_complaints.append("gummy_smile")
    else:
        ev.metrics.append(Metric("tooth_display", "歯の露出量", "—", NA, None,
                                 "歯列を検出できず判定不可。"))

    return ev


# --------------------------------------------------------------------------- #
# ミクロ評価（歯と歯肉）
# --------------------------------------------------------------------------- #
def evaluate_micro(img: np.ndarray) -> Evaluation:
    ev = Evaluation("micro", "ミクロ評価（歯と歯肉）")
    if img is None or img.size == 0:
        return ev

    (rx, ry, rw, rh), _ = _find_mouth_roi(img)
    roi = img[ry:ry + rh, rx:rx + rw]
    teeth, gum, dark = _masks(roi)

    # 1) 黄金比（前歯から遠心へ見かけ幅が約 0.618 で逓減しているか）
    widths = _tooth_widths(teeth)
    if len(widths) >= 3:
        widths.sort(key=lambda t: t[0])
        center = rw / 2.0
        # 中央から左右それぞれ遠心へ向けた連続歯の幅比（理想 ≈0.618）
        left_seq = [wd for cx, wd in sorted(widths, key=lambda t: -t[0]) if cx <= center]
        right_seq = [wd for cx, wd in sorted(widths, key=lambda t: t[0]) if cx > center]
        ratios = []
        for seq in (left_seq, right_seq):
            for i in range(len(seq) - 1):
                if seq[i] > 0:
                    ratios.append(seq[i + 1] / seq[i])
        if ratios:
            dev = float(np.mean([abs(r - 0.618) for r in ratios]))
            score = float(np.clip(1.0 - dev / 0.35, 0.0, 1.0))
            ev.metrics.append(
                Metric(
                    "golden_proportion", "歯のバランス（黄金比）",
                    f"隣接幅比の平均 {np.mean(ratios):.2f}（理想 0.62）/ 検出 {len(widths)} 歯",
                    _status_from_score(score), round(score, 2),
                    "前歯から遠心への見かけ幅の逓減比。理想は約 62%（ゴールデンプロポーション）。",
                )
            )
        else:
            ev.metrics.append(Metric("golden_proportion", "歯のバランス（黄金比）", "—", NA, None,
                                     "個々の歯を十分に分離できず判定不可。"))
    else:
        ev.metrics.append(Metric("golden_proportion", "歯のバランス（黄金比）", "—", NA, None,
                                 "個々の歯を十分に分離できず判定不可。"))

    # 2) 歯の色と透明感（L*=明度, C*=彩度, Hue=色相, 切縁の透明感）
    if teeth.sum() > 30:
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
        m = teeth.astype(bool)
        L = float(np.mean(lab[..., 0][m]))               # 0..255
        a = float(np.mean(lab[..., 1][m])) - 128.0
        b = float(np.mean(lab[..., 2][m])) - 128.0
        chroma = float(np.hypot(a, b))
        yellow = float(np.clip((b) / 32.0, 0.0, 1.0))
        # 透明感プロキシ: 切縁側 1/3 の明度ばらつき
        band = _teeth_band(teeth)
        translucency = 0.0
        if band is not None:
            x0, y0, w, h = band
            inc = teeth[y0 + int(h * 0.66):y0 + h, x0:x0 + w].astype(bool)
            if inc.sum() > 10:
                translucency = float(np.std(lab[..., 0][y0 + int(h * 0.66):y0 + h, x0:x0 + w][inc]))
        # 明るく黄色味が少ないほど高評価
        score = float(np.clip((L - 150) / 80.0, 0.0, 1.0)) * (1.0 - 0.5 * yellow)
        tone = "明るい" if L > 190 else ("中等度" if L > 150 else "暗め")
        ev.metrics.append(
            Metric(
                "color_translucency", "歯の色と透明感",
                f"明度 {L:.0f}/255（{tone}）, 彩度 {chroma:.0f}, 黄色味 {yellow * 100:.0f}%, "
                f"切縁透明感指標 {translucency:.0f}",
                _status_from_score(score), round(score, 2),
                "トーン（明度・彩度・色相）と切縁の明度ばらつき（透明感の代理指標）。WB の影響大。",
            )
        )
        if yellow > 0.5 or L < 150:
            ev.derived_complaints.append("discoloration")
    else:
        ev.metrics.append(Metric("color_translucency", "歯の色と透明感", "—", NA, None,
                                 "歯領域を検出できず判定不可。"))

    # 3) 歯の形態と質感（中切歯の縦横比＝丸み/角張り, 表面のテクスチャ）
    band = _teeth_band(teeth)
    if band is not None and widths:
        # 中央に最も近い歯を中切歯候補とする（細いノイズ片は除外）
        center = rw / 2.0
        med_w = float(np.median([wd for _cx, wd in widths]))
        candidates = [(cx, wd) for cx, wd in widths if wd >= 0.5 * med_w] or widths
        cx, cw = min(candidates, key=lambda t: abs(t[0] - center))
        # 歯の列範囲で高さの中央値をとる（単一列の欠けに頑健）
        x_lo = int(max(0, cx - cw / 2)); x_hi = int(min(rw, cx + cw / 2 + 1))
        heights = []
        for c in range(x_lo, x_hi):
            col = np.nonzero(teeth[:, c])[0]
            if col.size:
                heights.append(col.max() - col.min() + 1)
        ch = float(np.median(heights)) if heights else float(band[3])
        aspect = cw / max(ch, 1.0)  # 幅/高さ
        shape = "丸み・縦長傾向" if aspect < 0.78 else ("角張り・横広傾向" if aspect > 0.95 else "標準的")
        # 質感: 歯領域の高周波エネルギー（ラプラシアン分散）
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        texture = float(np.var(lap[teeth.astype(bool)])) if teeth.sum() > 10 else 0.0
        ev.metrics.append(
            Metric(
                "morphology_texture", "歯の形態と質感",
                f"中切歯の縦横比 {aspect:.2f}（{shape}）/ 表面質感指標 {texture:.0f}",
                REF, None,
                "歯冠の縦横比（顔貌との調和）と表面テクスチャ（マメロン・性状）の代理指標。",
            )
        )
    else:
        ev.metrics.append(Metric("morphology_texture", "歯の形態と質感", "—", NA, None,
                                 "歯を分離できず判定不可。"))

    # 4) 歯肉のラインと見え方（左右対称性・色調・ガミー）
    if gum.sum() > 30:
        # 歯列中心で左右に分割し歯肉面積の対称性を見る
        center_col = int(rw / 2)
        left_g = float(gum[:, :center_col].sum())
        right_g = float(gum[:, center_col:].sum())
        sym = 1.0 - abs(left_g - right_g) / max(left_g + right_g, 1.0)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gV = float(np.mean(hsv[..., 2][gum.astype(bool)]))
        pigmented = gV < 90  # 暗い歯肉=色素沈着の手がかり
        gum_ratio = float(gum.sum()) / max(float(teeth.sum()), 1.0)
        gummy = gum_ratio > 0.6
        score = float(np.clip(sym, 0.0, 1.0)) * (0.6 if (pigmented or gummy) else 1.0)
        desc = f"左右対称性 {sym * 100:.0f}%"
        if gummy:
            desc += " / 歯肉露出多（ガミー傾向）"
        if pigmented:
            desc += " / 暗色（色素沈着の可能性）"
        ev.metrics.append(
            Metric(
                "gingival", "歯肉のラインと見え方",
                desc, _status_from_score(score), round(score, 2),
                "歯肉ラインの左右対称性・色調・露出量。ピンク色で左右対称が望ましい。",
            )
        )
        if gummy:
            ev.derived_complaints.append("gummy_smile")
        if pigmented:
            ev.derived_complaints.append("gingival_pigmentation")
    else:
        ev.metrics.append(Metric("gingival", "歯肉のラインと見え方", "—", NA, None,
                                 "歯肉を検出できず判定不可。"))

    return ev


def evaluate(img: np.ndarray, kind: str) -> Evaluation:
    if kind == "macro":
        return evaluate_macro(img)
    if kind == "micro":
        return evaluate_micro(img)
    raise ValueError(f"kind は 'macro' か 'micro': {kind}")
