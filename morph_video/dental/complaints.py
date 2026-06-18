"""審美的な患者主訴のカタログ。

各主訴は治療提示・オート判定・レポートで共通のコードで参照する。
``auto_detectable`` は OpenCV ヒューリスティックで候補として拾える可能性が
あるものを示す（あくまで補助で、確定ではない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Complaint:
    code: str
    label: str  # 患者向けの平易な表記
    category: str  # 色調 / 歯列 / 形態 / 欠損 / 歯肉 / スマイル
    description: str
    keywords: List[str] = field(default_factory=list)
    auto_detectable: bool = False


# 審美歯科で頻度の高い主訴。順序はカテゴリでまとめてある。
_COMPLAINT_LIST: List[Complaint] = [
    # --- 色調 ---
    Complaint(
        code="discoloration",
        label="歯の変色・黄ばみ",
        category="色調",
        description="歯全体または一部の着色・黄ばみ・暗さが気になる。",
        keywords=["変色", "黄ばみ", "着色", "白くしたい", "黒ずみ"],
        auto_detectable=True,
    ),
    Complaint(
        code="metal_restoration",
        label="金属の詰め物・被せ物の色",
        category="色調",
        description="銀歯など金属色の補綴物が目立つのが気になる。",
        keywords=["銀歯", "メタル", "金属", "詰め物の色", "被せ物の色"],
        auto_detectable=True,
    ),
    Complaint(
        code="old_restoration_discoloration",
        label="補綴物の変色・段差",
        category="色調",
        description="既存の被せ物・詰め物の変色や歯ぐきとの境目の黒ずみ・不適合。",
        keywords=["被せ物の変色", "差し歯の変色", "境目の黒ずみ"],
        auto_detectable=True,
    ),
    # --- 歯列 ---
    Complaint(
        code="crowding",
        label="歯並びのガタつき（叢生・八重歯）",
        category="歯列",
        description="歯が重なって凸凹している、八重歯がある。",
        keywords=["ガタガタ", "叢生", "八重歯", "凸凹", "歯並び"],
        auto_detectable=False,
    ),
    Complaint(
        code="spacing",
        label="すきっ歯（空隙歯列）",
        category="歯列",
        description="歯と歯の間に隙間が空いている。",
        keywords=["すきっ歯", "隙間", "空隙"],
        auto_detectable=True,
    ),
    Complaint(
        code="diastema",
        label="前歯の正中の隙間（正中離開）",
        category="歯列",
        description="前歯の真ん中の隙間が気になる。",
        keywords=["正中離開", "前歯の隙間", "真ん中の隙間"],
        auto_detectable=True,
    ),
    Complaint(
        code="maxillary_protrusion",
        label="出っ歯（上顎前突）",
        category="歯列",
        description="上の前歯が前方に突出している。",
        keywords=["出っ歯", "上顎前突", "前歯が出ている"],
        auto_detectable=False,
    ),
    Complaint(
        code="mandibular_protrusion",
        label="受け口（下顎前突・反対咬合）",
        category="歯列",
        description="下の歯が上の歯より前に出ている。",
        keywords=["受け口", "下顎前突", "反対咬合", "しゃくれ"],
        auto_detectable=False,
    ),
    Complaint(
        code="bite_problem",
        label="噛み合わせの深さ（過蓋咬合・開咬）",
        category="歯列",
        description="噛み合わせが深い、または前歯が噛み合わない（開咬）。",
        keywords=["過蓋咬合", "開咬", "噛み合わせ", "前歯が噛まない"],
        auto_detectable=False,
    ),
    Complaint(
        code="midline_deviation",
        label="正中・スマイルラインの不一致",
        category="歯列",
        description="上下の正中がずれている、笑ったときの歯のラインが左右非対称。",
        keywords=["正中のずれ", "左右非対称", "ライン", "傾き"],
        auto_detectable=True,
    ),
    # --- 形態 ---
    Complaint(
        code="microdontia",
        label="歯の形・大きさ（矮小歯・形態異常）",
        category="形態",
        description="歯が小さい・とがっている・形が気になる。",
        keywords=["矮小歯", "歯が小さい", "形", "とがった歯"],
        auto_detectable=False,
    ),
    Complaint(
        code="wear_fracture",
        label="歯の咬耗・破折・欠け",
        category="形態",
        description="歯がすり減っている、欠けている、割れている。",
        keywords=["すり減り", "咬耗", "破折", "欠けた", "割れた"],
        auto_detectable=False,
    ),
    # --- 欠損 ---
    Complaint(
        code="missing_tooth",
        label="歯の欠損（抜けた歯）",
        category="欠損",
        description="歯が抜けたまま、または抜歯後の欠損がある。",
        keywords=["欠損", "抜けた歯", "歯がない", "入れ歯"],
        auto_detectable=True,
    ),
    # --- スマイル / 歯肉 ---
    Complaint(
        code="gummy_smile",
        label="ガミースマイル（歯ぐきの見えすぎ）",
        category="スマイル",
        description="笑ったときに歯ぐきが大きく見えるのが気になる。",
        keywords=["ガミースマイル", "歯ぐきが見える", "歯茎"],
        auto_detectable=True,
    ),
    Complaint(
        code="gingival_pigmentation",
        label="歯ぐきの色素沈着・黒ずみ",
        category="歯肉",
        description="歯ぐきの黒ずみ・色素沈着が気になる。",
        keywords=["歯茎の黒ずみ", "色素沈着", "メラニン"],
        auto_detectable=True,
    ),
]

COMPLAINTS: Dict[str, Complaint] = {c.code: c for c in _COMPLAINT_LIST}


def list_complaints() -> List[Complaint]:
    """カタログ順の主訴一覧。"""
    return list(_COMPLAINT_LIST)


def get_complaint(code: str) -> Complaint:
    try:
        return COMPLAINTS[code]
    except KeyError as exc:
        raise KeyError(
            f"未知の主訴コード '{code}'. 選択肢: {', '.join(COMPLAINTS)}"
        ) from exc
