"""SNS テンプレートと、動画フレームへのラベル/タイトル/ウォーターマーク合成。

日本語ラベルにも対応するため、テキスト描画は Pillow（CJK フォント）を使う。
フォントが見つからない場合は OpenCV (ASCII) にフォールバックする。
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

try:  # Pillow は任意（無ければ cv2 ASCII 描画）
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except Exception:  # pragma: no cover
    _PIL = False

# 日本語対応フォント候補（環境にある最初のものを使う）
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FONT_PATH = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)
_font_cache: Dict[int, "ImageFont.FreeTypeFont"] = {}


def _font(size: int):
    if not (_PIL and _FONT_PATH):
        return None
    f = _font_cache.get(size)
    if f is None:
        f = ImageFont.truetype(_FONT_PATH, size)
        _font_cache[size] = f
    return f


def draw_text(
    frame: np.ndarray,
    text: str,
    xy: Tuple[int, int],
    size: int,
    color=(255, 255, 255),
    anchor: str = "la",  # PIL anchor: l/m/r + a/m/s 等
    stroke: int = 3,
    stroke_fill=(0, 0, 0),
) -> np.ndarray:
    """frame(BGR) にテキストを描画して返す。"""
    if not text:
        return frame
    font = _font(size)
    if font is not None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        d = ImageDraw.Draw(img)
        d.text(
            xy, text, font=font, fill=tuple(color), anchor=anchor,
            stroke_width=stroke, stroke_fill=tuple(stroke_fill),
        )
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    # フォールバック: cv2（ASCII のみ）
    scale = size / 32.0
    x, y = xy
    cv2.putText(frame, text, (int(x), int(y + size * 0.8)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, stroke_fill, max(2, int(stroke) + 2), cv2.LINE_AA)
    cv2.putText(frame, text, (int(x), int(y + size * 0.8)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color[::-1], max(1, int(scale * 2)), cv2.LINE_AA)
    return frame


def _chip(frame: np.ndarray, x: int, y: int, w: int, h: int, color=(255, 255, 255), alpha=0.82):
    """半透明の角丸チップ（ラベル背景）。"""
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


# テンプレート定義
TEMPLATES: Dict[str, Dict] = {
    "minimal": {"label_name": "Minimal Clinical", "pos": "bl", "fill": "blur",
                "title": False, "watermark": True, "dots": False, "accent": False},
    "aesthetic": {"label_name": "Aesthetic Case", "pos": "bc", "fill": "gradient",
                  "title": True, "watermark": True, "dots": False, "accent": False},
    "beforeafter": {"label_name": "Before / After", "pos": "tl", "fill": "blur",
                    "title": False, "watermark": True, "dots": False, "accent": False},
    "timeline": {"label_name": "Treatment Timeline", "pos": "bl", "fill": "blur",
                 "title": True, "watermark": True, "dots": True, "accent": False},
    "smile": {"label_name": "Smile Design", "pos": "bc", "fill": "gradient",
              "title": True, "watermark": True, "dots": False, "accent": True},
    # Focus Clinical: 黒背景・口元フォーカスリング・微細ズーム・タイムラインで
    # 症例写真を臨床的に美しく見せる presentation テンプレート。
    "focus": {"label_name": "Focus Clinical", "pos": "bc", "fill": "black",
              "title": True, "watermark": True, "dots": True, "accent": True,
              "focus": True},
}

TEMPLATE_DEFAULT_FILL = {k: v["fill"] for k, v in TEMPLATES.items()}


def _hex_to_bgr(h: str) -> Tuple[int, int, int]:
    h = (h or "#7c5cff").lstrip("#")
    if len(h) != 6:
        h = "7c5cff"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


class TemplateRenderer:
    """テンプレートに従い、各フレームへラベル・タイトル・装飾を合成する。"""

    def __init__(self, template: str, title: str = "",
                 watermark: str = "Smile Morph Studio", colors=("#7c5cff", "#ff9fd6"),
                 roi: Optional[Tuple[float, float, float]] = None):
        self.cfg = TEMPLATES.get(template, TEMPLATES["minimal"])
        self.title = title or ""
        self.watermark = watermark if self.cfg["watermark"] else ""
        self.accent = _hex_to_bgr(colors[0]) if colors else (255, 92, 124)
        # focus 用: 口元 ROI（正規化 cx,cy,r）。共通 normalized data から渡す。
        self.roi = tuple(roi) if roi else (0.5, 0.62, 0.26)
        self._fi = 0                 # フレームカウンタ（ズーム/パルスの位相）
        self._vig_cache = None       # ビネットマスクのキャッシュ

    def __call__(self, frame: np.ndarray, label: str, idx: int, n: int) -> np.ndarray:
        h, w = frame.shape[:2]
        u = w / 1080.0  # 1080px 基準のスケール
        pos = self.cfg["pos"]
        lab_size = int(46 * u)

        # Focus Clinical: 微細ズーム → ビネット → 口元フォーカスリング/パルスを
        # 先に適用し、その上にラベル等を描く（presentation layer・幾何は非改変）。
        if self.cfg.get("focus"):
            frame = self._focus_present(frame)
            h, w = frame.shape[:2]
        self._fi += 1

        # タイトル（上部）
        if self.cfg["title"] and self.title:
            draw_text(frame, self.title, (int(w / 2), int(36 * u)), int(40 * u),
                      color=(255, 255, 255), anchor="ma")

        # タイムライン・ドット
        if self.cfg["dots"] and n > 1:
            r = max(4, int(7 * u))
            gap = r * 3
            total = gap * (n - 1)
            cx0 = w // 2 - total // 2
            cy = h - int(86 * u)
            for i in range(n):
                c = self.accent if i == idx else (210, 210, 210)
                cv2.circle(frame, (cx0 + i * gap, cy), r if i != idx else r + 2, c, -1, cv2.LINE_AA)

        # ラベル
        if label:
            pad = int(20 * u)
            tw = int(len(label) * lab_size * 0.62) + pad * 2
            th = int(lab_size * 1.5)
            if pos == "bl":
                x, y = int(40 * u), h - th - int(40 * u)
            elif pos == "tl":
                x, y = int(40 * u), int(40 * u)
            else:  # bc
                x, y = (w - tw) // 2, h - th - int(46 * u)
            if pos == "tl":  # Before/After は濃色タグ
                _chip(frame, x, y, tw, th, color=(53, 27, 32), alpha=0.78)
                txt_color = (255, 255, 255)
            else:
                _chip(frame, x, y, tw, th, color=(255, 255, 255), alpha=0.82)
                txt_color = (53, 27, 32)
            if self.cfg["accent"]:
                cv2.rectangle(frame, (x, y + th), (x + tw, y + th + max(2, int(4 * u))),
                              self.accent, -1, cv2.LINE_AA)
            draw_text(frame, label, (x + pad, y + int(th * 0.16)), lab_size,
                      color=txt_color, stroke=0 if pos != "tl" else 2,
                      stroke_fill=(0, 0, 0))

        # ウォーターマーク
        if self.watermark:
            draw_text(frame, self.watermark, (w - int(20 * u), h - int(20 * u)),
                      int(22 * u), color=(255, 255, 255), anchor="rs", stroke=2)
        return frame

    # ----------------------- Focus Clinical presentation ---------------------- #
    _ZOOM_PERIOD = 150   # 微細ズームの周期（フレーム）
    _PULSE_PERIOD = 66   # フォーカスリングのパルス周期（フレーム）

    def _focus_present(self, frame: np.ndarray) -> np.ndarray:
        """微細ズーム + ビネット + 口元フォーカスリング/パルスを合成して返す。"""
        h, w = frame.shape[:2]
        base = min(w, h)
        cx, cy, r = self.roi
        ccx, ccy = cx * w, cy * h
        fi = self._fi

        # 1) 微細ズーム（ROI 中心・1.0〜1.03 の緩やかな往復）— subtle zoom
        z = 1.0 + 0.030 * (0.5 - 0.5 * math.cos(2 * math.pi * (fi % self._ZOOM_PERIOD) / self._ZOOM_PERIOD))
        mat = cv2.getRotationMatrix2D((ccx, ccy), 0.0, z)
        frame = cv2.warpAffine(frame, mat, (w, h), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)

        # 2) ビネット（周辺を落として口元に視線誘導）— 落ち着いた臨床トーン
        frame = self._apply_vignette(frame, ccx, ccy, r * base)

        # 3) フォーカスリング（静的 1 重）+ パルス（1〜2 重の広がるリング）
        ring_r = r * base * 1.55
        self._draw_focus_rings(frame, ccx, ccy, ring_r, base, fi)
        return frame

    def _apply_vignette(self, frame, ccx, ccy, r_px):
        h, w = frame.shape[:2]
        cache = self._vig_cache
        if cache is None or cache[0] != (w, h):
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            d = np.sqrt((xx - ccx) ** 2 + (yy - ccy) ** 2)
            inner = max(1.0, r_px * 1.5)
            outer = max(inner + 1.0, float(max(w, h)) * 0.62)
            m = np.clip((outer - d) / (outer - inner), 0.0, 1.0)
            m = m * m * (3 - 2 * m)               # smoothstep
            floor = 0.42                          # 周辺の明るさ下限（暗すぎない）
            mask = (floor + (1.0 - floor) * m)[..., None]
            self._vig_cache = ((w, h), mask)
            cache = self._vig_cache
        out = frame.astype(np.float32) * cache[1]
        return np.clip(out, 0, 255).astype(np.uint8)

    def _draw_focus_rings(self, frame, ccx, ccy, ring_r, base, fi):
        """控えめな臨床トーン: 静的リング 1 + パルス 1 + 微細な走査弧のみ。

        過剰な SF 感を避けるため本数・不透明度を抑える。
        """
        cx, cy = int(round(ccx)), int(round(ccy))
        thin = max(2, int(base * 0.0032))
        accent = self.accent
        white = (255, 255, 255)

        # 静的リング（単一・細く淡く）
        ov = frame.copy()
        cv2.circle(ov, (cx, cy), int(ring_r), white, thin, cv2.LINE_AA)
        cv2.addWeighted(ov, 0.26, frame, 0.74, 0, frame)

        # パルス（1 本のみ・広がって消える radar 風）
        ph = (fi % self._PULSE_PERIOD) / self._PULSE_PERIOD
        pr = ring_r * (0.82 + 0.7 * ph)
        a = 0.30 * (1.0 - ph) ** 1.6
        if a > 0.02:
            ov = frame.copy()
            cv2.circle(ov, (cx, cy), int(pr), white, max(1, thin - 1), cv2.LINE_AA)
            cv2.addWeighted(ov, a, frame, 1 - a, 0, frame)

        # 微細な走査（scan）: ゆっくり回る短い弧（アクセント色・淡く）
        ov = frame.copy()
        ang = (fi * 1.7) % 360
        cv2.ellipse(ov, (cx, cy), (int(ring_r), int(ring_r)), 0, ang, ang + 36,
                    accent, thin, cv2.LINE_AA)
        cv2.addWeighted(ov, 0.24, frame, 0.76, 0, frame)


def make_renderer(template: str, title: str = "", colors=("#7c5cff", "#ff9fd6"),
                  roi: Optional[Tuple[float, float, float]] = None) -> TemplateRenderer:
    return TemplateRenderer(template, title=title, colors=colors, roi=roi)


def list_templates() -> List[Dict[str, str]]:
    return [{"id": k, "name": v["label_name"]} for k, v in TEMPLATES.items()]
