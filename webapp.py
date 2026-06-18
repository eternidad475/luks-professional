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
.preview{width:100%;aspect-ratio:4/3;background:#0b1220;border-radius:8px;object-fit:contain;display:block}
.row{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
button,.btn{font:inherit;border:1px solid var(--line);background:#fff;border-radius:8px;padding:8px 12px;cursor:pointer;display:inline-block}
.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.fields{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:18px}
label{font-size:13px;color:var(--muted);display:block;margin-bottom:4px}
input[type=text]{width:100%;padding:8px;border:1px solid var(--line);border-radius:8px;font:inherit}
.cam{position:fixed;inset:0;background:#000;display:none;flex-direction:column;z-index:50}
.camstage{flex:1;position:relative;min-height:0}
.camstage video{width:100%;height:100%;object-fit:contain;display:block}
.guide{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
.guide line,.guide ellipse,.guide rect,.guide path{fill:none;stroke:#34d399;stroke-width:1.4;
  opacity:.85;vector-effect:non-scaling-stroke}
.guide .mid{stroke:#fbbf24;stroke-dasharray:4 3}
.guidecap{position:absolute;top:10px;left:0;right:0;text-align:center;color:#d1fae5;
  font-size:13px;text-shadow:0 1px 3px #000;pointer-events:none;padding:0 12px}
.cam .bar{display:flex;justify-content:center;gap:16px;padding:16px;background:#111}
.cbtoggle{position:absolute;opacity:0;width:0;height:0}
.sheet{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:center;justify-content:center;z-index:60}
.cbtoggle:checked ~ .sheet{display:flex}
.sheet-box{background:#fff;border-radius:14px;padding:18px;width:min(360px,90vw);box-shadow:0 12px 40px rgba(0,0,0,.3)}
.sheet-box h3{margin:0 0 12px;font-size:15px;text-align:center;color:#1f2933}
.sheet-box .opt{display:block;width:100%;margin-top:10px;padding:12px;font-size:15px;text-align:center}
.sheet-box .opt.ghost{color:var(--muted);background:#f1f5f9}
.disclaimer{margin-top:24px;font-size:12px;background:#fffbea;border:1px solid #fde68a;color:#92400e;border-radius:8px;padding:12px}
.note{color:var(--muted);font-size:12px}
#status{margin-top:14px;font-size:14px}
</style></head>
<body><div class="wrap">
<h1>審美歯科 記録・シミュレーション</h1>
<p class="note">各スロットの「＋ 画像を追加」を押すと、カメラ撮影・写真ライブラリから選択・ファイルのアップロードを選べます。最低 1 枚で解析できます。</p>

<h2>マクロ（顔貌とスマイル）</h2>
<div class="grid">
  __SLOT_macro_before__
  __SLOT_macro_after__
</div>

<h2 class="micro">ミクロ（歯と歯肉）</h2>
<div class="grid">
  __SLOT_micro_before__
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

<div class="cam" id="cam">
  <div class="camstage">
    <video id="camvideo" autoplay playsinline muted></video>
    <svg class="guide" viewBox="0 0 100 100" preserveAspectRatio="none">
      <!-- マクロ（顔貌とスマイル）ガイド -->
      <g id="guide_macro" style="display:none">
        <ellipse cx="50" cy="52" rx="26" ry="41"></ellipse>
        <line class="mid" x1="50" y1="6" x2="50" y2="98"></line>
        <line x1="22" y1="34" x2="78" y2="34"></line>
        <line x1="30" y1="70" x2="70" y2="70"></line>
      </g>
      <!-- ミクロ（歯と歯肉）ガイド -->
      <g id="guide_micro" style="display:none">
        <rect x="10" y="28" width="80" height="44" rx="6"></rect>
        <line class="mid" x1="50" y1="22" x2="50" y2="78"></line>
        <line x1="12" y1="50" x2="88" y2="50"></line>
        <path d="M14,44 Q50,66 86,44"></path>
      </g>
    </svg>
    <div class="guidecap" id="guidecap"></div>
  </div>
  <div class="bar">
    <button id="camcancel">キャンセル</button>
    <button id="camswitch">カメラ切替</button>
    <button class="primary" id="camshot">撮影</button>
  </div>
</div>

<script>
const slots = ["macro_before","macro_after","micro_before","micro_after"];
const data = {};               // slot -> dataURL
let camStream=null, camTarget=null, facing="environment";

function setPreview(slot, url){
  data[slot]=url;
  document.getElementById("img_"+slot).src = url;
}

function closeSheet(slot){ const cb=document.getElementById("cb_"+slot); if(cb) cb.checked=false; }
function handleFile(slot, input){
  closeSheet(slot);
  const f=input.files[0]; if(!f) return;
  const r=new FileReader();
  r.onload=()=>setPreview(slot, r.result);
  r.readAsDataURL(f);
}
slots.forEach(slot=>{
  // ポップアップの開閉はチェックボックス（CSS）が担当。以下は実動作の補助。
  document.getElementById("lib_"+slot).addEventListener("change", e=>handleFile(slot, e.target));
  document.getElementById("file_"+slot).addEventListener("change", e=>handleFile(slot, e.target));
  document.getElementById("cam_"+slot).addEventListener("click", ()=>{ closeSheet(slot); openCam(slot); });
});

// 撮影ガイド（Invisalign 系の撮影アプリのように構図を合わせるための補助線）
const GUIDE_CAP={
  macro:"顔貌・スマイル: 顔の正中を黄色線に合わせ、瞳孔線を水平・上下の線に口唇を合わせて笑顔で撮影",
  micro:"歯・歯肉: 正中を黄色線に、咬合平面を水平線に合わせ、歯列を枠とアーチに収めて撮影"
};
function showGuide(kind){
  document.getElementById("guide_macro").style.display = kind==="macro"?"":"none";
  document.getElementById("guide_micro").style.display = kind==="micro"?"":"none";
  document.getElementById("guidecap").textContent = GUIDE_CAP[kind]||"";
}

// getUserMedia によるライブ撮影
async function openCam(slot){
  camTarget=slot;
  try{
    camStream=await navigator.mediaDevices.getUserMedia({video:{facingMode:facing}, audio:false});
  }catch(err){
    alert("カメラを起動できませんでした: "+err+"\\nアップロードをご利用ください。");
    return;
  }
  showGuide(slot.indexOf("macro")===0 ? "macro" : "micro");
  document.getElementById("camvideo").srcObject=camStream;
  document.getElementById("cam").style.display="flex";
}
function closeCam(){
  if(camStream){camStream.getTracks().forEach(t=>t.stop());camStream=null;}
  document.getElementById("cam").style.display="none";
}
document.getElementById("camcancel").onclick=closeCam;
document.getElementById("camswitch").onclick=async()=>{
  facing = facing==="environment"?"user":"environment";
  if(camTarget) {closeCam(); openCam(camTarget);}
};
document.getElementById("camshot").onclick=()=>{
  const v=document.getElementById("camvideo");
  const c=document.createElement("canvas");
  c.width=v.videoWidth; c.height=v.videoHeight;
  c.getContext("2d").drawImage(v,0,0);
  setPreview(camTarget, c.toDataURL("image/jpeg",0.9));
  closeCam();
};

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
    # ポップアップの開閉はチェックボックス（CSS）で行うため、JS 無効環境でも開く。
    # 写真ライブラリ/ファイルは label→input[type=file] で JS 無しでも選択可。
    # カメラ撮影のみ getUserMedia（JS 必須）。
    return f"""<div class="slot">
  <h3>{label}</h3>
  <img class="preview" id="img_{slot}" alt="{label}">
  <div class="row">
    <input type="checkbox" id="cb_{slot}" class="cbtoggle">
    <label class="btn primary" for="cb_{slot}">＋ 画像を追加</label>
    <div class="sheet">
      <div class="sheet-box">
        <h3>{label}<br>画像の取得方法を選択</h3>
        <button type="button" class="btn primary opt" id="cam_{slot}">📷 カメラで撮影</button>
        <label class="btn opt" for="lib_{slot}">🖼 写真ライブラリから選択</label>
        <label class="btn opt" for="file_{slot}">⬆ ファイルをアップロード</label>
        <label class="btn opt ghost" for="cb_{slot}">キャンセル</label>
      </div>
    </div>
    <input type="file" id="lib_{slot}" accept="image/*" style="display:none">
    <input type="file" id="file_{slot}" accept="image/*,.cr2,.cr3,.nef,.arw,.raf,.orf,.dng,.heic" style="display:none">
  </div>
</div>"""


def render_index() -> str:
    html = INDEX_HTML
    labels = {
        "macro_before": "術前（顔貌・スマイル）",
        "macro_after": "術後 / シミュレーション",
        "micro_before": "術前（歯・歯肉の接写）",
        "micro_after": "術後 / シミュレーション",
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
