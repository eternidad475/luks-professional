"""症例ワークフロー。

マクロ（顔貌とスマイル）／ミクロ（歯と歯肉）の 2 バージョンの画像を受け取り、
それぞれを評価し、術前/術後があればモーフィング動画を生成、主訴と推奨治療を
まとめて HTML/JSON レポートに統合する。
"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from ..io_utils import load_image
from ..pipeline import build_video
from .auto import AutoFinding
from .complaints import get_complaint
from .evaluation import Evaluation, evaluate
from .treatments import Recommendation, recommend_for_codes


@dataclass
class VersionData:
    """マクロ/ミクロ 1 バージョン分の画像・動画・評価。"""

    kind: str  # "macro" / "micro"
    title: str
    before_path: Optional[str] = None
    after_path: Optional[str] = None
    video_path: Optional[str] = None
    evaluation: Optional[Evaluation] = None
    before_image: Optional[np.ndarray] = field(default=None, repr=False)
    after_image: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class CaseResult:
    case_id: str = ""
    patient_label: str = ""
    date: str = ""
    versions: List[VersionData] = field(default_factory=list)
    auto_findings: List[AutoFinding] = field(default_factory=list)
    selected_codes: List[str] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    disclaimer: str = ""


_TITLES = {"macro": "マクロ評価（顔貌とスマイル）", "micro": "ミクロ評価（歯と歯肉）"}


def _build_version(
    kind: str,
    before: Optional[str],
    after: Optional[str],
    output_dir: str,
    do_eval: bool,
    method: str,
    fps: float,
    transition_seconds: float,
    hold_seconds: float,
    morpher_kwargs: Optional[dict],
    say: Callable[[str], None],
) -> Optional[VersionData]:
    if not before and not after:
        return None

    vd = VersionData(kind=kind, title=_TITLES[kind], before_path=before, after_path=after)
    if before:
        vd.before_image = load_image(before)
    if after:
        vd.after_image = load_image(after)

    # 評価（術前を優先、無ければ術後）
    if do_eval:
        target = vd.before_image if vd.before_image is not None else vd.after_image
        if target is not None:
            say(f"{vd.title}: 画像を解析中...")
            vd.evaluation = evaluate(target, kind)

    # 術前術後シミュレーション動画
    if before and after:
        video_path = os.path.join(output_dir, f"simulation_{kind}.mp4")
        say(f"{vd.title}: シミュレーション動画を生成中 ({method})...")
        build_video(
            inputs=[before, after],
            output=video_path,
            method=method,
            fps=fps,
            transition_seconds=transition_seconds,
            hold_seconds=hold_seconds,
            loop=True,
            morpher_kwargs=morpher_kwargs,
            progress=lambda m: say("  " + m),
        )
        vd.video_path = video_path
    return vd


def run_case(
    macro_before: Optional[str] = None,
    macro_after: Optional[str] = None,
    micro_before: Optional[str] = None,
    micro_after: Optional[str] = None,
    complaints: Optional[List[str]] = None,
    auto: bool = True,
    case_id: str = "",
    patient_label: str = "",
    output_dir: str = "report",
    method: str = "flow",
    fps: float = 30.0,
    transition_seconds: float = 1.5,
    hold_seconds: float = 1.0,
    morpher_kwargs: Optional[dict] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> CaseResult:
    """1 症例分の処理（評価・シミュレーション・推奨提示・レポート出力）。

    macro_* はマクロ（顔貌とスマイル）、micro_* はミクロ（歯と歯肉）の画像。
    各バージョンで before/after が揃えばモーフィング動画を生成する。
    """
    from . import DISCLAIMER, report

    say = progress or (lambda _m: None)
    os.makedirs(output_dir, exist_ok=True)

    result = CaseResult(
        case_id=case_id,
        patient_label=patient_label,
        date=_dt.date.today().isoformat(),
        disclaimer=DISCLAIMER,
    )

    for kind, before, after in (
        ("macro", macro_before, macro_after),
        ("micro", micro_before, micro_after),
    ):
        vd = _build_version(
            kind, before, after, output_dir, auto, method, fps,
            transition_seconds, hold_seconds, morpher_kwargs, say,
        )
        if vd is not None:
            result.versions.append(vd)

    # 評価から導かれた主訴候補（バージョン横断・重複除去）
    derived: List[str] = []
    for vd in result.versions:
        if vd.evaluation:
            for code in vd.evaluation.derived_complaints:
                if code not in derived:
                    derived.append(code)
    result.auto_findings = [
        AutoFinding(code, 0.0, {}, "評価項目から導かれた主訴候補") for code in derived
    ]

    # 主訴の確定（手動指定 + 評価由来候補をマージ、手動優先）
    manual = list(complaints or [])
    for c in manual:
        get_complaint(c)
    merged: List[str] = []
    for c in manual + derived:
        if c not in merged:
            merged.append(c)
    result.selected_codes = merged
    result.recommendations = recommend_for_codes(result.selected_codes)

    # レポート出力
    html_path = os.path.join(output_dir, "report.html")
    json_path = os.path.join(output_dir, "case.json")
    report.write_html(result, html_path)
    report.write_json(result, json_path)
    say(f"レポート出力: {html_path}")
    say(f"JSON 出力: {json_path}")
    return result
