#!/usr/bin/env python3
"""歯科 審美シミュレーション Web UI（標準ライブラリのみ）。

スマホ（iPhone 等）のカメラで直接撮影する方法と、一眼レフ等で撮影した画像を
アップロードする方法の両方に対応する。マクロ（顔貌・スマイル）／ミクロ（歯・
歯肉）それぞれに術前・術後のスロットを用意し、送信すると評価・推奨治療・
シミュレーション動画・レポートを生成して結果ページへ遷移する。

起動:
    python webapp.py            # http://localhost:8000
    python webapp.py --port 9000 --host 0.0.0.0

注意: 出力は記録・患者説明・シミュレーションの補助を目的とした参考情報であり、
確定診断・治療方針の決定を代替するものではありません。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional

from morph_video.dental import DISCLAIMER, run_case

# 生成物の保存先（症例ごとにサブフォルダ）
OUTPUT_ROOT = os.environ.get("DENTAL_OUTPUT_ROOT", os.path.join(tempfile.gettempdir(), "dental_reports"))

# スロット定義: (フォーム名, run_case 引数名)
SLOTS = [
    ("macro_before", "macro_before"),
    ("macro_after", "macro_after"),
    ("micro_before", "micro_before"),
    ("micro_after", "micro_after"),
]

_DATAURL_RE = re.compile(r"^data:image/(\w+);base64,(.+)$", re.DOTALL)


def _save_data_url(data_url: str, dest_dir: str, name: str) -> Optional[str]:
    m = _DATAURL_RE.match(data_url or "")
    if not m:
        return None
    ext = m.group(1).lower()
    ext = "jpg" if ext in ("jpeg", "jpg") else ext
    path = os.path.join(dest_dir, f"{name}.{ext}")
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(m.group(2)))
    return path


INDEX_HTML = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>審美シミュレーション 撮影・アップロード</title>
<style>
:root{--accent:#2563eb;--line:#e3e8ee;--muted:#6b7785;}
*{box-sizing:border-box}
body{font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;margin:0;background:#f7f9fb;color:#1f2933;line-height:1.6}
.wrap{max-width:880px;margin:0 auto;padding:20px}
h1{font-size:20px} h2{font-size:16px;border-left:4px solid #6366f1;padding-left:8px;margin-top:26px}
h2.micro{border-color:#0d9488}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
.slot{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}
.slot h3{margin:0 0 8px;font-size:14px}
.preview{width:100%;aspect-ratio:4/3;background:#0b1220;border-radius:8px;object-fit:contain;display:block;border:2px solid var(--line)}
.preview.set{border-color:#16a34a}
.row{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
button,.btn{font:inherit;border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px 12px;cursor:pointer;display:inline-block}
.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.fields{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:18px}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:4px}
input[type=text]{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;font:inherit}
.addbtn{display:block;width:100%;text-align:center}
.disclaimer{margin-top:24px;font-size:12px;background:#fffbea;border:1px solid #fde68a;color:#92400e;border-radius:8px;padding:12px}
.note{color:var(--muted);font-size:12px}
#status{margin-top:14px;font-size:14px}
</style></head>
<body><div class="wrap">
<h1>審美歯科 記録・シミュレーション</h1>
<p class="note">各スロットの「＋ 画像を追加」を押すと、端末標準のメニュー（写真を撮る／写真ライブラリ／ファイルを選択）が表示されます。評価用画像が 1 枚あれば解析できます。</p>

<h2>① 評価用画像（現状）</h2>
<p class="note">審美評価（マクロ4項目・ミクロ4項目）に使用します。シミュレーションを行う場合は、この画像が「術前」になります。</p>
<div class="grid">
  __SLOT_macro_before__
  __SLOT_micro_before__
</div>

<h2 class="micro">② シミュレーション用画像（術後イメージ・任意）</h2>
<p class="note">「評価用画像 → この画像」へのモーフィング動画を生成します。シミュレーションが不要なら空のままで構いません。</p>
<div class="grid">
  __SLOT_macro_after__
  __SLOT_micro_after__
</div>

<div class="fields">
  <div class="grid">
    <div><label>症例 ID</label><input type="text" id="case_id" placeholder="例: C001"></div>
    <div><label>患者ラベル（イニシャル等）</label><input type="text" id="patient" placeholder="例: T.S."></div>
  </div>
  <div class="row" style="margin-top:12px">
    <label style="margin:0"><input type="checkbox" id="auto" checked> 自動評価を行う</label>
  </div>
  <div class="row" style="margin-top:12px">
    <button class="primary" id="run">解析してレポート生成</button>
  </div>
  <div id="status"></div>
</div>

<div class="disclaimer">__DISCLAIMER__</div>
</div>

<script>
const slots = ["macro_before","macro_after","micro_before","micro_after"];
const data = {};               // slot -> dataURL

function setPreview(slot, url){
  data[slot]=url;
  const img=document.getElementById("img_"+slot);
  img.src = url;
  img.classList.add("set");
}

// 選択画像を canvas で縮小し JPEG dataURL に変換する。
// iPhone の HEIC を JPEG 化して表示可能にし、向き補正・容量削減も行う。
function fileToDataURL(file, maxDim){
  return new Promise((resolve)=>{
    const url=URL.createObjectURL(file);
    const img=new Image();
    img.onload=()=>{
      let w=img.naturalWidth||img.width, h=img.naturalHeight||img.height;
      const scale=Math.min(1, maxDim/Math.max(w,h));
      const cw=Math.max(1,Math.round(w*scale)), ch=Math.max(1,Math.round(h*scale));
      const c=document.createElement("canvas"); c.width=cw; c.height=ch;
      c.getContext("2d").drawImage(img,0,0,cw,ch);
      URL.revokeObjectURL(url);
      try{ resolve(c.toDataURL("image/jpeg",0.9)); }
      catch(e){ resolve(null); }
    };
    img.onerror=()=>{   // HEIC 等で img 読み込み不可なら FileReader にフォールバック
      URL.revokeObjectURL(url);
      const r=new FileReader();
      r.onload=()=>resolve(r.result);
      r.onerror=()=>resolve(null);
      r.readAsDataURL(file);
    };
    img.src=url;
  });
}

// 「＋ 画像を追加」は単一の file input を開くだけ。
// 写真を撮る/写真ライブラリ/ファイル選択は端末標準メニューに委譲する。
async function handleFile(slot, input){
  const f=input.files[0]; if(!f) return;
  const url=await fileToDataURL(f, 1600);
  if(url){ setPreview(slot, url); }
  else { alert("この画像を読み込めませんでした。別の形式（JPEG/PNG）でお試しください。"); }
}
slots.forEach(slot=>{
  document.getElementById("file_"+slot).addEventListener("change", e=>handleFile(slot, e.target));
});

document.getElementById("run").onclick=async()=>{
  const imgs={};
  slots.forEach(s=>{ if(data[s]) imgs[s]=data[s]; });
  if(Object.keys(imgs).length===0){ alert("少なくとも 1 枚の画像が必要です。"); return; }
  const status=document.getElementById("status");
  status.textContent="解析中... しばらくお待ちください。";
  const payload={
    images:imgs,
    case_id:document.getElementById("case_id").value,
    patient:document.getElementById("patient").value,
    auto:document.getElementById("auto").checked
  };
  try{
    const res=await fetch("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const j=await res.json();
    if(j.ok){ window.location = j.report_url; }
    else { status.textContent="エラー: "+(j.error||"不明"); }
  }catch(err){ status.textContent="通信エラー: "+err; }
};
</script>
</body></html>"""


def _slot_html(slot: str, label: str) -> str:
    # 「＋ 画像を追加」ラベルが file input を直接開く。
    # 端末側が標準メニュー（写真を撮る/写真ライブラリ/ファイルを選択）を表示する。
    return f"""<div class="slot">
  <h3>{label}</h3>
  <img class="preview" id="img_{slot}" alt="{label}">
  <div class="row">
    <label class="btn primary addbtn" for="file_{slot}">＋ 画像を追加</label>
    <input type="file" id="file_{slot}" accept="image/*" style="display:none">
  </div>
</div>"""


def render_index() -> str:
    html = INDEX_HTML
    labels = {
        "macro_before": "マクロ｜顔貌・スマイル（評価用）",
        "micro_before": "ミクロ｜歯・歯肉（評価用）",
        "macro_after": "マクロ｜顔貌・スマイル（術後イメージ）",
        "micro_after": "ミクロ｜歯・歯肉（術後イメージ）",
    }
    for slot, label in labels.items():
        html = html.replace(f"__SLOT_{slot}__", _slot_html(slot, label))
    html = html.replace("__DISCLAIMER__", DISCLAIMER)
    return html


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静かなログ
        return

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, render_index().encode("utf-8"), "text/html; charset=utf-8")
            return
        # 生成物の配信: /reports/<case>/<file>
        if self.path.startswith("/reports/"):
            rel = self.path[len("/reports/"):].split("?")[0]
            safe = os.path.normpath(rel).lstrip("/")
            full = os.path.join(OUTPUT_ROOT, safe)
            if os.path.commonpath([os.path.abspath(full), os.path.abspath(OUTPUT_ROOT)]) != os.path.abspath(OUTPUT_ROOT):
                self._send(403, b"forbidden", "text/plain")
                return
            if not os.path.isfile(full):
                self._send(404, b"not found", "text/plain")
                return
            ctype = "text/html; charset=utf-8" if full.endswith(".html") else (
                "video/mp4" if full.endswith(".mp4") else (
                    "application/json" if full.endswith(".json") else "application/octet-stream"))
            with open(full, "rb") as fh:
                self._send(200, fh.read(), ctype)
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/analyze":
            self._send(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result_url = self._run_analysis(payload)
            self._send(200, json.dumps({"ok": True, "report_url": result_url}).encode("utf-8"),
                       "application/json")
        except Exception as exc:  # noqa: BLE001
            self._send(200, json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"),
                       "application/json")

    def _run_analysis(self, payload: Dict) -> str:
        case = uuid.uuid4().hex[:10]
        case_dir = os.path.join(OUTPUT_ROOT, case)
        os.makedirs(case_dir, exist_ok=True)

        images = payload.get("images", {})
        kwargs = {}
        for form_name, arg_name in SLOTS:
            if form_name in images:
                saved = _save_data_url(images[form_name], case_dir, form_name)
                if saved:
                    kwargs[arg_name] = saved

        if not kwargs:
            raise ValueError("有効な画像がありません。")

        run_case(
            complaints=[],
            auto=bool(payload.get("auto", True)),
            case_id=payload.get("case_id", "") or case,
            patient_label=payload.get("patient", ""),
            output_dir=case_dir,
            method="flow",
            **kwargs,
        )
        return f"/reports/{case}/report.html"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="歯科 審美シミュレーション Web UI")
    p.add_argument("--host", default="127.0.0.1", help="バインドするホスト")
    p.add_argument("--port", type=int, default=8000, help="ポート")
    args = p.parse_args(argv)

    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"審美シミュレーション Web UI: http://{args.host}:{args.port}")
    print(f"生成物の保存先: {OUTPUT_ROOT}")
    print("※ スマホのカメラ撮影には HTTPS もしくは localhost が必要な場合があります。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
