"""モーフィングの進行度 t (0..1) に対するイージング関数。

遷移の出だしと終わりを滑らかにすることで、より自然な動画になります。
"""

from __future__ import annotations

import math
from typing import Callable, Dict


def linear(t: float) -> float:
    return t


def ease_in_out(t: float) -> float:
    """smoothstep。両端がゆっくり、中央が速い。"""
    return t * t * (3.0 - 2.0 * t)


def ease_in_out_sine(t: float) -> float:
    return 0.5 * (1.0 - math.cos(math.pi * t))


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) * (1.0 - t)


EASINGS: Dict[str, Callable[[float], float]] = {
    "linear": linear,
    "ease_in_out": ease_in_out,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_in": ease_in,
    "ease_out": ease_out,
}


def get_easing(name: str) -> Callable[[float], float]:
    try:
        return EASINGS[name]
    except KeyError as exc:  # pragma: no cover - 入力バリデーション
        raise ValueError(
            f"未知のイージング '{name}'. 選択肢: {', '.join(EASINGS)}"
        ) from exc
