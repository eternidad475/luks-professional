"""症例ワークフロー。

マクロ（顔貌とスマイル）／ミクロ（歯と歯肉）の 2 バージョンについて、評価用の
画像シーケンス（複数枚）と任意のシミュレーション用画像（術後イメージ）を受け取る。

- 評価: 各バージョンの評価用シーケンス先頭画像で審美評価を行う
- シーケンス動画: 評価用が 2 枚以上ならシーケンスをモーフィングして動画化
- シミュレーション動画: 術後イメージがあれば「評価用末尾 → 術後イメージ」を動画化
- 主訴・推奨治療・各動画をまとめて HTML/JSON レポートに統合（動画はダウンロード可）
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
    eval_paths: List[str] = field(default_factory=list)   # 評価用シーケンス（順序つき）
    target_path: Optional[str] = None                     # 術後イメージ（任意）
    seq_video_path: Optional[str] = None                  # 評価用シーケンスの動画
    sim_video_path: Optional[str] = None                  # 評価用→術後イメージの動画
    evaluation: Optional[Evaluation] = None
    eval_images: List[np.ndarray] = field(default_factory=list, repr=False)
    target_image: Optional[np.ndarray] = field(default=None, repr=False)


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
    eval_paths: List[str],
    target_path: Optional[str],
    output_dir: str,
    do_eval: bool,
    method: str,
    fps: float,
    transition_seconds: float,
    hold_seconds: float,
    aspect: Optional[str],
    fill: str,
    morpher_kwargs: Optional[dict],
    say: Callable[[str], None],
) -> Optional[VersionData]:
    eval_paths = [p for p in (eval_paths or []) if p]
    if not eval_paths and not target_path:
        return None

    vd = VersionData(
        kind=kind, title=_TITLES[kind], eval_paths=eval_paths, target_path=target_path
    )
    vd.eval_images = [load_image(p) for p in eval_paths]
    if target_path:
        vd.target_image = load_image(target_path)

    # 審美評価（評価用シーケンス先頭を優先、無ければ術後イメージ）
    if do_eval:
        target = vd.eval_images[0] if vd.eval_images else vd.target_image
        if target is not None:
            say(f"{vd.title}: 画像を解析中...")
            vd.evaluation = evaluate(target, kind)

    def _morph(inputs: List[str], out_name: str, loop: bool) -> str:
        out = os.path.join(output_dir, out_name)
        build_video(
            inputs=inputs,
            output=out,
            method=method,
            fps=fps,
            transition_seconds=transition_seconds,
            hold_seconds=hold_seconds,
            loop=loop,
            aspect=aspect,
            fill=fill,
            morpher_kwargs=morpher_kwargs,
            progress=lambda m: say("  " + m),
        )
        return out

    # 評価用シーケンスのモーフィング動画（2 枚以上）
    if len(eval_paths) >= 2:
        say(f"{vd.title}: シーケンス動画を生成中（{len(eval_paths)} 枚, {method}）...")
        vd.seq_video_path = _morph(eval_paths, f"sequence_{kind}.mp4", loop=False)

    # 術前→術後イメージのシミュレーション動画
    if target_path and eval_paths:
        say(f"{vd.title}: シミュレーション動画を生成中 ({method})...")
        vd.sim_video_path = _morph(
            [eval_paths[-1], target_path], f"simulation_{kind}.mp4", loop=True
        )
    return vd


def run_case(
    macro_eval: Optional[List[str]] = None,
    micro_eval: Optional[List[str]] = None,
    macro_target: Optional[str] = None,
    micro_target: Optional[str] = None,
    complaints: Optional[List[str]] = None,
    auto: bool = True,
    case_id: str = "",
    patient_label: str = "",
    output_dir: str = "report",
    method: str = "flow",
    fps: float = 30.0,
    transition_seconds: float = 1.5,
    hold_seconds: float = 1.0,
    aspect: Optional[str] = None,
    fill: str = "blur",
    morpher_kwargs: Optional[dict] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> CaseResult:
    """1 症例分の処理（評価・シーケンス/シミュレーション動画・推奨提示・レポート出力）。

    ``macro_eval`` / ``micro_eval`` は評価用画像シーケンス（順序つきの複数枚）。
    ``macro_target`` / ``micro_target`` は任意の術後イメージ（シミュレーション用）。
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

    for kind, evals, target in (
        ("macro", macro_eval, macro_target),
        ("micro", micro_eval, micro_target),
    ):
        vd = _build_version(
            kind, evals or [], target, output_dir, auto, method, fps,
            transition_seconds, hold_seconds, aspect, fill, morpher_kwargs, say,
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
