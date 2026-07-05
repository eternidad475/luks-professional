"""モーフィング方式の実装。

すべての Morpher は ``frame(img1, img2, t) -> ndarray`` を実装する。
t は 0..1 で、0 のとき img1、1 のとき img2 に一致する中間フレームを返す。
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Sequence, Tuple, Type

import cv2
import numpy as np


def _blend(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """(1-t)*a + t*b を uint8 で返す。"""
    return cv2.addWeighted(a, 1.0 - t, b, t, 0.0)


class Morpher:
    """モーフィング方式の基底クラス。"""

    name = "base"

    def frame(self, img1: np.ndarray, img2: np.ndarray, t: float) -> np.ndarray:
        raise NotImplementedError

    def prepare(self, img1: np.ndarray, img2: np.ndarray) -> None:
        """ペアごとの前計算 (任意)。frame の前に一度だけ呼ばれる。"""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} name={self.name!r}>"


# --------------------------------------------------------------------------- #
# 1. クロスフェード (変形なし)
# --------------------------------------------------------------------------- #
class CrossfadeMorpher(Morpher):
    """単純なアルファブレンド。最も軽量で高速。"""

    name = "crossfade"

    def frame(self, img1: np.ndarray, img2: np.ndarray, t: float) -> np.ndarray:
        if t <= 0.0:
            return img1
        if t >= 1.0:
            return img2
        return _blend(img1, img2, t)


# --------------------------------------------------------------------------- #
# 2. オプティカルフロー
# --------------------------------------------------------------------------- #
class OpticalFlowMorpher(Morpher):
    """Farneback オプティカルフローで画素の動きを推定し、変形しながら合成する。

    img1->img2 と img2->img1 の双方向フローを求め、中間時刻 t で両者を
    変形させてからクロスディゾルブする。手作業の対応点指定なしに、人物や
    風景など一般的な写真で自然な変形が得られる。
    """

    name = "flow"

    def __init__(
        self,
        pyr_scale: float = 0.5,
        levels: int = 5,
        winsize: int = 25,
        iterations: int = 3,
        poly_n: int = 5,
        poly_sigma: float = 1.2,
    ):
        self.params = dict(
            pyr_scale=pyr_scale,
            levels=levels,
            winsize=winsize,
            iterations=iterations,
            poly_n=poly_n,
            poly_sigma=poly_sigma,
            flags=0,
        )
        self._flow_12 = None
        self._flow_21 = None
        self._grid = None

    def prepare(self, img1: np.ndarray, img2: np.ndarray) -> None:
        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
        self._flow_12 = cv2.calcOpticalFlowFarneback(g1, g2, None, **self.params)
        self._flow_21 = cv2.calcOpticalFlowFarneback(g2, g1, None, **self.params)
        h, w = img1.shape[:2]
        gx, gy = np.meshgrid(np.arange(w), np.arange(h))
        self._grid = (gx.astype(np.float32), gy.astype(np.float32))

    def _warp(self, img: np.ndarray, flow: np.ndarray, scale: float) -> np.ndarray:
        gx, gy = self._grid
        map_x = gx + scale * flow[..., 0]
        map_y = gy + scale * flow[..., 1]
        return cv2.remap(
            img,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

    def frame(self, img1: np.ndarray, img2: np.ndarray, t: float) -> np.ndarray:
        if t <= 0.0:
            return img1
        if t >= 1.0:
            return img2
        if self._flow_12 is None:
            self.prepare(img1, img2)
        # img1 を t だけ img2 方向へ、img2 を (1-t) だけ img1 方向へ変形
        warped1 = self._warp(img1, self._flow_12, t)
        warped2 = self._warp(img2, self._flow_21, 1.0 - t)
        return _blend(warped1, warped2, t)


# --------------------------------------------------------------------------- #
# 3. 特徴点ベース (Delaunay 三角形分割ワープ)
# --------------------------------------------------------------------------- #
def _apply_affine(
    src: np.ndarray, src_tri: np.ndarray, dst_tri: np.ndarray, size: Tuple[int, int]
) -> np.ndarray:
    mat = cv2.getAffineTransform(np.float32(src_tri), np.float32(dst_tri))
    return cv2.warpAffine(
        src,
        mat,
        (size[0], size[1]),
        None,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )


def _morph_triangle(
    img1: np.ndarray,
    img2: np.ndarray,
    out: np.ndarray,
    tri1: np.ndarray,
    tri2: np.ndarray,
    tri: np.ndarray,
    t: float,
) -> None:
    """1 つの三角形について img1/img2 を中間形状にワープしてブレンドし out に書き込む。"""
    r1 = cv2.boundingRect(np.float32([tri1]))
    r2 = cv2.boundingRect(np.float32([tri2]))
    r = cv2.boundingRect(np.float32([tri]))

    # バウンディングボックス内のローカル座標へ変換
    t1_rect = [(p[0] - r1[0], p[1] - r1[1]) for p in tri1]
    t2_rect = [(p[0] - r2[0], p[1] - r2[1]) for p in tri2]
    t_rect = [(p[0] - r[0], p[1] - r[1]) for p in tri]

    mask = np.zeros((r[3], r[2], 3), dtype=np.float32)
    cv2.fillConvexPoly(mask, np.int32(t_rect), (1.0, 1.0, 1.0), cv2.LINE_AA, 0)

    img1_rect = img1[r1[1]:r1[1] + r1[3], r1[0]:r1[0] + r1[2]]
    img2_rect = img2[r2[1]:r2[1] + r2[3], r2[0]:r2[0] + r2[2]]
    if img1_rect.size == 0 or img2_rect.size == 0:
        return

    size = (r[2], r[3])
    warped1 = _apply_affine(img1_rect, t1_rect, t_rect, size)
    warped2 = _apply_affine(img2_rect, t2_rect, t_rect, size)
    blended = (1.0 - t) * warped1.astype(np.float32) + t * warped2.astype(np.float32)

    # 三角形マスクの内側だけを合成 (はみ出し防止)
    region = out[r[1]:r[1] + r[3], r[0]:r[0] + r[2]].astype(np.float32)
    region = region * (1.0 - mask) + blended * mask
    out[r[1]:r[1] + r[3], r[0]:r[0] + r[2]] = np.clip(region, 0, 255).astype(np.uint8)


def _delaunay_indices(
    size: Tuple[int, int], points: np.ndarray
) -> List[Tuple[int, int, int]]:
    """点群に対する Delaunay 三角形分割を行い、各三角形を点インデックスで返す。"""
    w, h = size
    rect = (0, 0, w, h)
    subdiv = cv2.Subdiv2D(rect)
    for p in points:
        subdiv.insert((float(p[0]), float(p[1])))

    # 点 -> インデックスの逆引き (浮動小数の丸め誤差に強い辞書)
    index_of = {(round(float(p[0]), 1), round(float(p[1]), 1)): i for i, p in enumerate(points)}

    triangles = subdiv.getTriangleList()
    result: List[Tuple[int, int, int]] = []
    for tri in triangles:
        pts = [(tri[0], tri[1]), (tri[2], tri[3]), (tri[4], tri[5])]
        # 矩形外の点を含む三角形はスキップ
        if any(not (0 <= x <= w and 0 <= y <= h) for x, y in pts):
            continue
        idx = []
        for x, y in pts:
            key = (round(float(x), 1), round(float(y), 1))
            if key not in index_of:
                break
            idx.append(index_of[key])
        if len(idx) == 3:
            result.append((idx[0], idx[1], idx[2]))
    return result


class FeatureMorpher(Morpher):
    """ORB 特徴点の対応関係を使った三角形ワープモーフィング。

    両画像から特徴点を検出・マッチングし、外れ値を RANSAC で除去した上で
    Delaunay 三角形分割を構築。各三角形をアフィン変換でワープしながら合成する。
    顔・物体などはっきりした構造を持つ画像で、より正確な「変形」が得られる。
    対応点が十分に取れない場合は自動的にクロスフェードへフォールバックする。
    """

    name = "feature"

    def __init__(self, max_features: int = 2000, ratio: float = 0.75, min_matches: int = 12):
        self.max_features = max_features
        self.ratio = ratio
        self.min_matches = min_matches
        self._pts1 = None
        self._pts2 = None
        self._triangles = None
        self._fallback = False

    @staticmethod
    def _border_points(w: int, h: int) -> np.ndarray:
        """画像全体を覆うための境界点 (四隅 + 各辺の中点)。"""
        return np.array(
            [
                [0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1],
                [(w - 1) / 2, 0], [(w - 1), (h - 1) / 2],
                [(w - 1) / 2, h - 1], [0, (h - 1) / 2],
            ],
            dtype=np.float32,
        )

    def prepare(self, img1: np.ndarray, img2: np.ndarray) -> None:
        h, w = img1.shape[:2]
        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(self.max_features)
        kp1, des1 = orb.detectAndCompute(g1, None)
        kp2, des2 = orb.detectAndCompute(g2, None)

        good_src: List[Sequence[float]] = []
        good_dst: List[Sequence[float]] = []
        if des1 is not None and des2 is not None and len(kp1) >= 2 and len(kp2) >= 2:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
            knn = matcher.knnMatch(des1, des2, k=2)
            for pair in knn:
                if len(pair) < 2:
                    continue
                m, n = pair
                if m.distance < self.ratio * n.distance:
                    good_src.append(kp1[m.queryIdx].pt)
                    good_dst.append(kp2[m.trainIdx].pt)

        # src/dst は「対応点が十分にあるとき」だけ定義される。未定義参照 (NameError)
        # を避けるため先に None で初期化し、フォールバック判定を明示的に行う。
        src = dst = None
        if len(good_src) >= self.min_matches:
            src = np.float32(good_src)
            dst = np.float32(good_dst)
            # RANSAC で幾何的な外れ値を除去（findHomography は 4 点以上が必要）。
            if len(src) >= 4:
                _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
                if mask is not None:
                    inliers = mask.ravel().astype(bool)
                    # インライアが十分残る場合のみ絞り込む（全滅時は元の対応点を維持）。
                    if int(inliers.sum()) >= self.min_matches:
                        src, dst = src[inliers], dst[inliers]

        # 対応点不足（そもそも少ない／RANSAC 後に不足）は明示的にクロスフェードへ。
        if src is None or dst is None or len(src) < self.min_matches:
            warnings.warn(
                "対応点が不足しているためクロスフェードにフォールバックします。",
                RuntimeWarning,
            )
            self._fallback = True
            self._pts1 = self._pts2 = self._triangles = None
            return

        border = self._border_points(w, h)
        pts1 = np.vstack([src, border]).astype(np.float32)
        pts2 = np.vstack([dst, border]).astype(np.float32)

        # 矩形内へクランプ (Subdiv2D の挿入失敗を防ぐ)
        pts1[:, 0] = np.clip(pts1[:, 0], 0, w - 1)
        pts1[:, 1] = np.clip(pts1[:, 1], 0, h - 1)
        pts2[:, 0] = np.clip(pts2[:, 0], 0, w - 1)
        pts2[:, 1] = np.clip(pts2[:, 1], 0, h - 1)

        # 三角形の接続関係は中間形状 (t=0.5) で一度だけ求めて全 t で使い回す
        mid = 0.5 * (pts1 + pts2)
        self._pts1, self._pts2 = pts1, pts2
        self._triangles = _delaunay_indices((w, h), mid)
        self._fallback = False

    def frame(self, img1: np.ndarray, img2: np.ndarray, t: float) -> np.ndarray:
        if t <= 0.0:
            return img1
        if t >= 1.0:
            return img2
        if self._triangles is None and not self._fallback:
            self.prepare(img1, img2)
        if self._fallback:
            return _blend(img1, img2, t)

        pts = (1.0 - t) * self._pts1 + t * self._pts2
        out = np.zeros_like(img1)
        for a, b, c in self._triangles:
            tri1 = self._pts1[[a, b, c]]
            tri2 = self._pts2[[a, b, c]]
            tri = pts[[a, b, c]]
            _morph_triangle(img1, img2, out, tri1, tri2, tri, t)
        return out


MORPHERS: Dict[str, Type[Morpher]] = {
    CrossfadeMorpher.name: CrossfadeMorpher,
    OpticalFlowMorpher.name: OpticalFlowMorpher,
    FeatureMorpher.name: FeatureMorpher,
}


def get_morpher(name: str, **kwargs) -> Morpher:
    """名前から Morpher を生成する。"""
    try:
        cls = MORPHERS[name]
    except KeyError as exc:
        raise ValueError(
            f"未知のモーフィング方式 '{name}'. 選択肢: {', '.join(MORPHERS)}"
        ) from exc
    return cls(**kwargs)
