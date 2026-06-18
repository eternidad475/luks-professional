"""症例レポートの生成（自己完結 HTML と機械可読 JSON）。

HTML は患者説明用に術前/術後画像を base64 で埋め込み、シミュレーション動画は
同じ出力フォルダ内のファイルを ``<video>`` で参照する。JSON は電子カルテ等との
連携用。
"""

from __future__ import annotations

import base64
import dataclasses
import html
import json
import os
from typing import TYPE_CHECKING, Dict, List, Optional

import cv2
import numpy as np

from .complaints import get_complaint
from .treatments import Recommendation

if TYPE_CHECKING:  # pragma: no cover
    from .workflow import CaseResult


def _img_data_uri(img: Optional[np.ndarray]) -> Optional[str]:
    if img is None:
        return None
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def case_to_dict(result: "CaseResult") -> Dict:
    """CaseResult を JSON 化可能な dict に変換。"""
    findings = [dataclasses.asdict(f) for f in result.auto_findings]
    recs = []
    for r in result.recommendations:
        c = get_complaint(r.code)
        recs.append(
            {
                "code": r.code,
                "complaint_label": c.label,
                "category": c.category,
                "referral_note": r.referral_note,
                "options": [
                    {
                        "name": o.name,
                        "category": o.category,
                        "description": o.description,
                        "invasiveness": o.invasiveness,
                        "note": o.note,
                    }
                    for o in r.options
                ],
            }
        )
    return {
        "case_id": result.case_id,
        "patient_label": result.patient_label,
        "date": result.date,
        "images": {
            "before": result.before_path,
            "after": result.after_path,
        },
        "simulation_video": result.video_path,
        "auto_findings": findings,
        "selected_complaints": [
            {"code": c, "label": get_complaint(c).label} for c in result.selected_codes
        ],
        "recommendations": recs,
        "disclaimer": result.disclaimer,
    }


def _jsonable(obj):
    """numpy スカラ/配列を素の Python 型へ変換する json.dump 用ハンドラ。"""
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"JSON 変換できない型: {type(obj)!r}")


def write_json(result: "CaseResult", path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            case_to_dict(result), fh, ensure_ascii=False, indent=2, default=_jsonable
        )
    return path


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_CSS = """
:root { --fg:#1f2933; --muted:#677; --line:#e3e8ee; --ortho:#2563eb; --prostho:#0d9488; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif;
  color: var(--fg); margin: 0; background: #f7f9fb; line-height: 1.6; }
.wrap { max-width: 960px; margin: 0 auto; padding: 24px; }
header { border-bottom: 2px solid var(--line); padding-bottom: 12px; margin-bottom: 20px; }
h1 { font-size: 20px; margin: 0 0 4px; }
.meta { color: var(--muted); font-size: 13px; }
h2 { font-size: 16px; border-left: 4px solid #94a3b8; padding-left: 8px; margin: 28px 0 12px; }
.media { display: flex; gap: 16px; flex-wrap: wrap; }
.media figure { flex: 1 1 280px; margin: 0; }
.media img, .media video { width: 100%; border-radius: 8px; border: 1px solid var(--line); background:#000; }
figcaption { font-size: 13px; color: var(--muted); margin-top: 4px; text-align: center; }
.tags span { display:inline-block; background:#eef2f7; border-radius: 14px; padding: 3px 12px;
  margin: 0 6px 6px 0; font-size: 13px; }
.tags .auto { background:#fff7ed; border:1px solid #fed7aa; }
.card { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:14px; }
.card h3 { margin: 0 0 4px; font-size: 15px; }
.card .cat { font-size:12px; color: var(--muted); }
.opt { border-top: 1px dashed var(--line); padding: 10px 0; }
.opt:first-of-type { border-top: none; }
.badge { font-size:12px; font-weight:600; color:#fff; border-radius: 6px; padding: 2px 8px; margin-right:8px; }
.badge.ortho { background: var(--ortho); }
.badge.prostho { background: var(--prostho); }
.inv { font-size:12px; color: var(--muted); margin-left: 6px; }
.opt p { margin: 4px 0 0; font-size: 14px; }
.referral { background:#fef2f2; border:1px solid #fecaca; color:#991b1b; font-size:13px;
  border-radius:8px; padding:8px 12px; margin-top:8px; }
.conf { display:inline-block; width:120px; height:8px; background:#eee; border-radius:4px; vertical-align:middle; overflow:hidden; }
.conf > i { display:block; height:100%; background:#f59e0b; }
.findings li { margin-bottom:6px; font-size:14px; list-style:none; }
.findings ul { padding-left: 0; }
.disclaimer { margin-top: 28px; font-size: 12px; color:#7a4; background:#fffbea;
  border:1px solid #fde68a; color:#92400e; border-radius:8px; padding:12px 14px; }
"""


def _media_block(result: "CaseResult") -> str:
    parts: List[str] = []
    before_uri = _img_data_uri(result.before_image)
    after_uri = _img_data_uri(result.after_image)
    if before_uri:
        parts.append(
            f'<figure><img src="{before_uri}" alt="術前"/><figcaption>術前</figcaption></figure>'
        )
    if after_uri:
        parts.append(
            f'<figure><img src="{after_uri}" alt="術後/シミュレーション"/>'
            f"<figcaption>術後 / シミュレーション</figcaption></figure>"
        )
    if result.video_path:
        vid = html.escape(os.path.basename(result.video_path))
        parts.append(
            f'<figure><video controls loop muted playsinline><source src="{vid}" '
            f'type="video/mp4"></video><figcaption>モーフィング動画</figcaption></figure>'
        )
    if not parts:
        return ""
    return '<h2>記録画像 / シミュレーション</h2><div class="media">' + "".join(parts) + "</div>"


def _findings_block(result: "CaseResult") -> str:
    if not result.auto_findings:
        return ""
    rows = []
    for f in result.auto_findings:
        label = html.escape(get_complaint(f.code).label)
        pct = int(round(f.confidence * 100))
        note = html.escape(f.note)
        rows.append(
            f'<li><b>{label}</b> '
            f'<span class="conf"><i style="width:{pct}%"></i></span> 信頼度 {pct}%'
            f'<br><span class="meta">{note}</span></li>'
        )
    return (
        '<h2>オート判定（補助・要確認）</h2>'
        '<div class="findings"><ul>' + "".join(rows) + "</ul></div>"
    )


def _complaints_block(result: "CaseResult") -> str:
    if not result.selected_codes:
        return ""
    auto_codes = {f.code for f in result.auto_findings}
    tags = []
    for code in result.selected_codes:
        label = html.escape(get_complaint(code).label)
        cls = "auto" if code in auto_codes else ""
        suffix = " (オート)" if code in auto_codes else ""
        tags.append(f'<span class="{cls}">{label}{suffix}</span>')
    return '<h2>確定した審美的主訴</h2><div class="tags">' + "".join(tags) + "</div>"


def _recommend_block(result: "CaseResult") -> str:
    if not result.recommendations:
        return ""
    cards = []
    for r in result.recommendations:
        c = get_complaint(r.code)
        opts = []
        for o in r.options:
            cls = "ortho" if o.category == "歯列矯正" else "prostho"
            opts.append(
                f'<div class="opt"><span class="badge {cls}">{html.escape(o.category)}</span>'
                f"<b>{html.escape(o.name)}</b>"
                f'<span class="inv">侵襲度: {html.escape(o.invasiveness)}</span>'
                f"<p>{html.escape(o.description)}</p>"
                + (f'<p class="meta">{html.escape(o.note)}</p>' if o.note else "")
                + "</div>"
            )
        if not opts:
            opts.append('<p class="meta">矯正・補綴の適応となる治療はありません。</p>')
        referral = (
            f'<div class="referral">⚠ {html.escape(r.referral_note)}</div>'
            if r.referral_note
            else ""
        )
        cards.append(
            f'<div class="card"><h3>{html.escape(c.label)}</h3>'
            f'<div class="cat">{html.escape(c.category)}</div>'
            + "".join(opts)
            + referral
            + "</div>"
        )
    return (
        '<h2>推奨される治療（歯列矯正・補綴治療／美容整形・外科は対象外）</h2>'
        + "".join(cards)
    )


def render_html(result: "CaseResult") -> str:
    title = html.escape(result.patient_label or result.case_id or "症例レポート")
    meta_bits = [b for b in [result.case_id, result.date] if b]
    meta = html.escape(" / ".join(meta_bits))
    body = "".join(
        [
            _media_block(result),
            _findings_block(result),
            _complaints_block(result),
            _recommend_block(result),
        ]
    )
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - 審美シミュレーションレポート</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<header><h1>審美歯科 記録・シミュレーションレポート</h1>
<div class="meta">{title}{(' ｜ ' + meta) if meta else ''}</div></header>
{body}
<div class="disclaimer">{html.escape(result.disclaimer)}</div>
</div></body></html>"""


def write_html(result: "CaseResult", path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(result))
    return path
