"""morph_video - 複数の画像をモーフィングでつないで動画にするライブラリ。

3 つのモーフィング方式を選べます:

- ``crossfade``: 単純なアルファブレンド (変形なし、最速)
- ``flow``    : オプティカルフローで画素の動きを推定して変形しながら合成
- ``feature`` : 特徴点対応 + Delaunay 三角形分割によるワープモーフィング
"""

from .morphers import (
    MORPHERS,
    CrossfadeMorpher,
    FeatureMorpher,
    Morpher,
    OpticalFlowMorpher,
    get_morpher,
)
from .pipeline import build_video
from .normalize import (
    CoreLandmarks,
    ManualAdjust,
    auto_mouth_roi,
    core_landmarks,
    normalize_case,
    normalize_image,
    two_layer_mesh,
)

__all__ = [
    "MORPHERS",
    "Morpher",
    "CrossfadeMorpher",
    "OpticalFlowMorpher",
    "FeatureMorpher",
    "get_morpher",
    "build_video",
    # 共通正規化 / ランドマーク / メッシュの基盤
    "ManualAdjust",
    "CoreLandmarks",
    "normalize_image",
    "normalize_case",
    "core_landmarks",
    "two_layer_mesh",
    "auto_mouth_roi",
]

__version__ = "0.1.0"
