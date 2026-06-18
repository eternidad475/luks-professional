"""推奨治療のナレッジベースと提示ロジック。

提示する治療は **歯列矯正 (ORTHO) と補綴治療 (PROSTHO) に限定** し、
美容整形・外科的処置 (顎変形症手術、歯肉整形、ガムピーリング等) は対象外とする。
外科・美容が主たる適応となりうる主訴には ``referral_note`` で専門医相談を促す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

ORTHO = "歯列矯正"
PROSTHO = "補綴治療"
ALLOWED_CATEGORIES = (ORTHO, PROSTHO)


@dataclass(frozen=True)
class TreatmentOption:
    name: str
    category: str  # ORTHO もしくは PROSTHO
    description: str
    invasiveness: str = "中"  # 低 / 中 / 高 の目安
    note: str = ""

    def __post_init__(self):
        if self.category not in ALLOWED_CATEGORIES:
            raise ValueError(
                f"治療カテゴリは {ALLOWED_CATEGORIES} のいずれかである必要があります"
                f"（美容整形・外科は対象外）: {self.category}"
            )


@dataclass
class Recommendation:
    code: str
    options: List[TreatmentOption] = field(default_factory=list)
    referral_note: str = ""  # 矯正/補綴の範囲外（外科・美容等）への注意喚起


# アライナー / ワイヤーは複数主訴で再利用するため定義しておく
_ALIGNER = TreatmentOption(
    "マウスピース型矯正（アライナー）",
    ORTHO,
    "透明なマウスピースを段階交換して歯を移動。軽〜中等度に適応、目立ちにくい。",
    invasiveness="低",
)
_WIRE = TreatmentOption(
    "マルチブラケット装置（ワイヤー矯正）",
    ORTHO,
    "ブラケットとワイヤーで幅広い不正咬合に対応。中〜重度にも適応。",
    invasiveness="中",
)
_BONDING = TreatmentOption(
    "ダイレクトボンディング（コンポジットレジン）",
    PROSTHO,
    "歯を削らずレジンを直接接着し形態・色調・小さな隙間を低侵襲に修正。",
    invasiveness="低",
)
_VENEER = TreatmentOption(
    "ラミネートベニア",
    PROSTHO,
    "歯の表面を薄く削りセラミックを接着。色調・形態・軽度の歯列を改善。",
    invasiveness="中",
)
_CROWN = TreatmentOption(
    "オールセラミッククラウン",
    PROSTHO,
    "歯全体をセラミックで被覆。重度変色・破折・大きな形態修正に適応。",
    invasiveness="高",
)


# 主訴コード -> 推奨内容
_KB: Dict[str, Recommendation] = {
    "discoloration": Recommendation(
        "discoloration",
        [
            _BONDING,
            _VENEER,
            _CROWN,
        ],
        referral_note="生活歯の表層的な着色のみであればホワイトニング（漂白）が"
        "第一選択となる場合があります（本提示の矯正・補綴の範囲外）。",
    ),
    "metal_restoration": Recommendation(
        "metal_restoration",
        [
            TreatmentOption(
                "メタルフリー修復（セラミックインレー/アンレー）",
                PROSTHO,
                "金属の詰め物をセラミック等の白い修復に置換し審美性を改善。",
                invasiveness="中",
            ),
            _CROWN,
        ],
    ),
    "old_restoration_discoloration": Recommendation(
        "old_restoration_discoloration",
        [
            _CROWN,
            _VENEER,
            TreatmentOption(
                "補綴物の再製作（オールセラミック等への置換）",
                PROSTHO,
                "変色・適合不良の既存補綴物をやり替え、辺縁の黒ずみや段差を改善。",
                invasiveness="中",
            ),
        ],
    ),
    "crowding": Recommendation(
        "crowding",
        [_ALIGNER, _WIRE],
        referral_note="重度の骨格性叢生では抜歯や外科的矯正の検討が必要な場合があり"
        "ます（外科は本提示の範囲外）。精密検査での評価を推奨します。",
    ),
    "spacing": Recommendation(
        "spacing",
        [
            _ALIGNER,
            _WIRE,
            _BONDING,
            _VENEER,
        ],
    ),
    "diastema": Recommendation(
        "diastema",
        [
            TreatmentOption(
                "部分矯正（前歯部のアライナー/ワイヤー）",
                ORTHO,
                "前歯部に限局した移動で正中の隙間を閉鎖。",
                invasiveness="低",
            ),
            _BONDING,
            _VENEER,
        ],
    ),
    "maxillary_protrusion": Recommendation(
        "maxillary_protrusion",
        [_WIRE, _ALIGNER],
        referral_note="骨格性の上顎前突では外科的矯正の適応となることがあります"
        "（外科は本提示の範囲外）。セファロ等での精密検査を推奨します。",
    ),
    "mandibular_protrusion": Recommendation(
        "mandibular_protrusion",
        [_WIRE],
        referral_note="骨格性の下顎前突（顎変形症）は外科的矯正の適応となることが"
        "多く、本提示（矯正・補綴）の範囲を超えます。専門医への相談を推奨します。",
    ),
    "bite_problem": Recommendation(
        "bite_problem",
        [_WIRE, _ALIGNER],
        referral_note="重度の開咬・過蓋咬合は外科的矯正や咬合再構成が必要となる"
        "場合があります。精密検査での評価を推奨します。",
    ),
    "midline_deviation": Recommendation(
        "midline_deviation",
        [
            _WIRE,
            _ALIGNER,
            TreatmentOption(
                "補綴的な歯冠形態修正",
                PROSTHO,
                "ベニア/クラウンで歯冠形態を整え、見た目の正中・スマイルラインを調整。",
                invasiveness="中",
            ),
        ],
    ),
    "microdontia": Recommendation(
        "microdontia",
        [
            _VENEER,
            _CROWN,
            TreatmentOption(
                "矯正によるスペース調整",
                ORTHO,
                "矮小歯の補綴に先立ち、適切な歯冠幅となるよう歯間スペースを矯正で配分。",
                invasiveness="中",
            ),
        ],
    ),
    "wear_fracture": Recommendation(
        "wear_fracture",
        [
            _BONDING,
            _VENEER,
            _CROWN,
        ],
    ),
    "missing_tooth": Recommendation(
        "missing_tooth",
        [
            TreatmentOption(
                "ブリッジ",
                PROSTHO,
                "両隣の歯を支台に連結した補綴で欠損部を補う。",
                invasiveness="高",
            ),
            TreatmentOption(
                "部分床義歯（入れ歯）",
                PROSTHO,
                "着脱式の補綴。複数歯欠損にも対応し非侵襲的。",
                invasiveness="低",
            ),
            TreatmentOption(
                "インプラント補綴（上部構造）",
                PROSTHO,
                "埋入したインプラント体に補綴物を装着。隣在歯を削らない。",
                invasiveness="高",
            ),
            TreatmentOption(
                "矯正的スペースクローズ",
                ORTHO,
                "隣在歯を移動させて欠損スペースを閉鎖する（適応は限定的）。",
                invasiveness="中",
            ),
        ],
    ),
    "gummy_smile": Recommendation(
        "gummy_smile",
        [
            TreatmentOption(
                "前歯部の圧下（矯正用アンカースクリュー併用）",
                ORTHO,
                "前歯を歯肉側へ移動させ、笑った際の歯肉露出を軽減。",
                invasiveness="中",
            ),
        ],
        referral_note="原因が上顎骨の過成長や歯肉形態による場合、歯肉整形・外科的"
        "処置が適応となることがありますが、これらは本提示の範囲外です。",
    ),
    # 矯正・補綴の適応外（歯肉処置）。提示は空とし注意喚起のみ。
    "gingival_pigmentation": Recommendation(
        "gingival_pigmentation",
        [],
        referral_note="歯ぐきの色素沈着はガムピーリング等の歯肉処置が対象であり、"
        "歯列矯正・補綴治療の適応ではありません。担当歯科医にご相談ください。",
    ),
}


def recommend(code: str) -> Recommendation:
    """主訴コードに対する推奨治療（矯正・補綴に限定）を返す。"""
    if code not in _KB:
        # カタログにあるが KB 未登録の場合も空で安全に返す
        return Recommendation(code, [], referral_note="登録された推奨治療がありません。")
    return _KB[code]


def recommend_for_codes(codes: List[str]) -> List[Recommendation]:
    """複数主訴に対する推奨をまとめて返す（入力順、重複は除去）。"""
    seen = set()
    out: List[Recommendation] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(recommend(c))
    return out
