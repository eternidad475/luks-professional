"""歯科臨床向けモジュール。

術前術後の記録撮影・シミュレーション動画に、審美的主訴の選択（オート判定つき）と
推奨治療（美容整形を除外し、歯列矯正・補綴治療に限定）の提示を組み合わせる。

重要: 本モジュールの出力は記録・患者説明・シミュレーションの補助を目的とした
参考情報であり、確定診断や治療方針の決定を代替するものではない。最終判断は
歯科医師の診察・検査に基づくこと。
"""

from __future__ import annotations

from .complaints import (
    COMPLAINTS,
    Complaint,
    get_complaint,
    list_complaints,
)
from .treatments import (
    TreatmentOption,
    recommend,
    recommend_for_codes,
)
from .auto import AutoFinding, detect_complaints
from .evaluation import (
    Evaluation,
    Metric,
    evaluate,
    evaluate_macro,
    evaluate_micro,
)
from .workflow import CaseResult, VersionData, run_case

DISCLAIMER = (
    "本ツールの出力は歯科臨床における記録・患者説明・シミュレーションの補助を"
    "目的とした参考情報であり、確定診断・治療方針の決定を代替するものではありません。"
    "オート判定は画像解析に基づく補助的な候補であり、必ず歯科医師が診察・検査の上で"
    "確認・修正してください。なお推奨治療は歯列矯正・補綴治療に限定して提示し、"
    "美容整形・外科的処置は対象外です（該当する場合は専門医への相談を促します）。"
)

__all__ = [
    "COMPLAINTS",
    "Complaint",
    "get_complaint",
    "list_complaints",
    "TreatmentOption",
    "recommend",
    "recommend_for_codes",
    "AutoFinding",
    "detect_complaints",
    "Evaluation",
    "Metric",
    "evaluate",
    "evaluate_macro",
    "evaluate_micro",
    "CaseResult",
    "VersionData",
    "run_case",
    "DISCLAIMER",
]
