"""症例ワークフロー: オート判定 → 主訴確定 → シミュレーション動画 → レポート。"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np

from ..io_utils import load_image
from ..pipeline import build_video
from .auto import AutoFinding, detect_complaints
from .complaints import get_complaint
from .treatments import Recommendation, recommend_for_codes


@dataclass
class CaseResult:
    case_id: str = ""
    patient_label: str = ""
    date: str = ""
    before_path: Optional[str] = None
    after_path: Optional[str] = None
    video_path: Optional[str] = None
    auto_findings: List[AutoFinding] = field(default_factory=list)
    selected_codes: List[str] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    disclaimer: str = ""
    # レポート埋め込み用（シリアライズ対象外）
    before_image: Optional[np.ndarray] = field(default=None, repr=False)
    after_image: Optional[np.ndarray] = field(default=None, repr=False)


def run_case(
    before: Optional[str] = None,
    after: Optional[str] = None,
    complaints: Optional[List[str]] = None,
    auto: bool = True,
    auto_min_confidence: float = 0.35,
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
    """1 症例分の処理を実行し、HTML/JSON とシミュレーション動画を出力する。

    Parameters
    ----------
    before, after:
        術前・術後（または術後シミュレーション）の画像パス。両方あればモーフィング
        動画を生成する。before のみでもオート判定・推奨提示は可能。
    complaints:
        術者が手動で確定した主訴コードの一覧。
    auto:
        True なら before（無ければ after）画像から主訴候補をオート判定する。
    """
    # 遅延 import で循環参照を回避
    from . import DISCLAIMER, report

    say = progress or (lambda _m: None)
    os.makedirs(output_dir, exist_ok=True)

    result = CaseResult(
        case_id=case_id,
        patient_label=patient_label,
        date=_dt.date.today().isoformat(),
        before_path=before,
        after_path=after,
        disclaimer=DISCLAIMER,
    )

    if before:
        result.before_image = load_image(before)
    if after:
        result.after_image = load_image(after)

    # 1) オート判定（解析対象は術前を優先）
    auto_codes: List[str] = []
    if auto:
        target = result.before_image if result.before_image is not None else result.after_image
        if target is not None:
            say("オート判定: 画像を解析中...")
            result.auto_findings = detect_complaints(target, auto_min_confidence)
            auto_codes = [f.code for f in result.auto_findings]
            if auto_codes:
                say("  候補: " + ", ".join(get_complaint(c).label for c in auto_codes))
            else:
                say("  自動候補は検出されませんでした（手動選択を推奨）。")

    # 2) 主訴の確定（手動指定 + オート候補をマージ、手動を優先順位で先に）
    manual = list(complaints or [])
    for c in manual:
        get_complaint(c)  # 妥当性チェック
    merged: List[str] = []
    for c in manual + auto_codes:
        if c not in merged:
            merged.append(c)
    result.selected_codes = merged

    # 3) 推奨治療（矯正・補綴に限定）
    result.recommendations = recommend_for_codes(result.selected_codes)

    # 4) 術前術後シミュレーション動画（両画像があるとき）
    if before and after:
        video_path = os.path.join(output_dir, "simulation.mp4")
        say(f"シミュレーション動画を生成中 ({method})...")
        build_video(
            inputs=[before, after],
            output=video_path,
            method=method,
            fps=fps,
            transition_seconds=transition_seconds,
            hold_seconds=hold_seconds,
            loop=True,  # 術前⇔術後を往復するループ
            morpher_kwargs=morpher_kwargs,
            progress=lambda m: say("  " + m),
        )
        result.video_path = video_path

    # 5) レポート出力
    html_path = os.path.join(output_dir, "report.html")
    json_path = os.path.join(output_dir, "case.json")
    report.write_html(result, html_path)
    report.write_json(result, json_path)
    say(f"レポート出力: {html_path}")
    say(f"JSON 出力: {json_path}")

    return result
