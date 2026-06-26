"""morph_video - 複数の画像をモーフィングでつないで動画にするライブラリ。

4 つのモーフィング方式を選べます:

- ``crossfade`` : 単純なアルファブレンド (変形なし、最速)
- ``flow``      : オプティカルフローで画素の動きを推定して変形しながら合成
- ``feature``   : 特徴点対応 + Delaunay 三角形分割によるワープモーフィング
- ``warp_only`` : 特徴点対応 + Delaunay 三角形分割。全画面クロスフェードを避け、透過感を抑える
"""

from .morphers import (
    MORPHERS,
    CrossfadeMorpher,
    FeatureMorpher,
    Morpher,
    OpticalFlowMorpher,
    WarpOnlyFeatureMorpher,
    get_morpher,
)
from .pipeline import build_video

__all__ = [
    "MORPHERS",
    "Morpher",
    "CrossfadeMorpher",
    "OpticalFlowMorpher",
    "FeatureMorpher",
    "WarpOnlyFeatureMorpher",
    "get_morpher",
    "build_video",
]

__version__ = "0.1.0"
