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
body{font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;margin:0;color:#15403d;line-height:1.6;
  background:linear-gradient(120deg,#bdeae5,#fff6cf);overflow-x:hidden}
/* ティファニーブルー×イエローがマーブル状に混ざって動く背景 */
body::before,body::after{content:"";position:fixed;inset:-30%;z-index:-1;pointer-events:none}
body::before{
  background:
    radial-gradient(40% 40% at 25% 30%, rgba(10,186,181,.78), transparent 60%),
    radial-gradient(45% 45% at 80% 22%, rgba(255,214,77,.72), transparent 60%),
    radial-gradient(50% 50% at 65% 80%, rgba(129,216,208,.82), transparent 62%),
    radial-gradient(45% 45% at 18% 82%, rgba(255,236,158,.78), transparent 62%);
  filter:blur(60px) saturate(1.15);
  animation:marbleA 24s ease-in-out infinite alternate}
body::after{
  background:
    radial-gradient(42% 42% at 70% 38%, rgba(10,186,181,.55), transparent 60%),
    radial-gradient(42% 42% at 30% 62%, rgba(255,209,59,.5), transparent 60%),
    radial-gradient(38% 38% at 50% 50%, rgba(167,232,227,.5), transparent 60%);
  filter:blur(80px);mix-blend-mode:screen;
  animation:marbleB 33s ease-in-out infinite alternate}
@keyframes marbleA{
  0%{transform:translate(-4%,-2%) rotate(0deg) scale(1.10)}
  50%{transform:translate(3%,4%) rotate(8deg) scale(1.26)}
  100%{transform:translate(-2%,3%) rotate(-6deg) scale(1.16)}}
@keyframes marbleB{
  0%{transform:translate(3%,2%) rotate(0deg) scale(1.18)}
  100%{transform:translate(-4%,-3%) rotate(12deg) scale(1.38)}}
@media(prefers-reduced-motion:reduce){body::before,body::after{animation:none}}
.wrap{max-width:880px;margin:18px auto;padding:20px;
  background:rgba(255,255,255,.5);backdrop-filter:blur(9px) saturate(1.1);
  -webkit-backdrop-filter:blur(9px) saturate(1.1);border-radius:18px;
  box-shadow:0 10px 34px rgba(13,80,76,.12)}
h1{font-size:20px;text-shadow:0 1px 2px rgba(255,255,255,.6)}
h2{font-size:16px;border-left:4px solid #0d9488;padding-left:8px;margin-top:26px;text-shadow:0 1px 2px rgba(255,255,255,.5)}
h2.micro{border-color:#caa204}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
.slot{background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px}
.slot h3{margin:0 0 8px;font-size:14px}
.preview{width:100%;aspect-ratio:4/3;background:#0b1220;border-radius:8px;object-fit:contain;display:block;border:2px solid var(--line)}
.preview.set{border-color:#16a34a}
.thumbs{display:flex;gap:6px;flex-wrap:wrap;min-height:8px}
.thumb{position:relative;width:64px;height:64px;border-radius:6px;overflow:hidden;border:1px solid var(--line);background:#0b1220}
.thumb img{width:100%;height:100%;object-fit:cover}
.thumb .no{position:absolute;left:2px;top:1px;font-size:10px;color:#fff;background:rgba(0,0,0,.55);border-radius:4px;padding:0 4px}
.thumb .rm{position:absolute;right:1px;top:1px;width:18px;height:18px;line-height:16px;text-align:center;
  border:none;border-radius:50%;background:rgba(0,0,0,.6);color:#fff;cursor:pointer;padding:0;font-size:13px}
.empty{color:var(--muted);font-size:12px;padding:6px 0}
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

<h2>① 評価用画像（シーケンス）</h2>
<p class="note">審美評価に使用します。複数枚を順番に追加でき、その並び順でモーフィング動画を生成・ダウンロードできます（評価は先頭画像で実施）。</p>
<div class="grid">
  __SEQ_macro_eval__
  __SEQ_micro_eval__
</div>

<h2 class="micro">② シミュレーション用画像（術後イメージ・任意）</h2>
<p class="note">「評価用の最後の画像 → この画像」へのモーフィング動画を生成します。不要なら空のままで構いません。</p>
<div class="grid">
  __SLOT_macro_target__
  __SLOT_micro_target__
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
const SEQS = ["macro_eval","micro_eval"];      // 評価用シーケンス（複数枚）
const TARGETS = ["macro_target","micro_target"]; // 術後イメージ（単一）
const seqs = {macro_eval:[], micro_eval:[]};    // slot -> [dataURL...]
const single = {};                              // target slot -> dataURL

function setPreview(slot, url){
  single[slot]=url;
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

// 単一画像（術後イメージ）のプレビュー
async function handleSingle(slot, input){
  const f=input.files[0]; input.value="";
  if(!f) return;
  const url=await fileToDataURL(f, 1600);
  if(url){ setPreview(slot, url); }
  else { alert("この画像を読み込めませんでした。別の形式（JPEG/PNG）でお試しください。"); }
}

// 評価用シーケンス（複数枚）のサムネイル・プレビュー
function renderThumbs(slot){
  const box=document.getElementById("thumbs_"+slot);
  const arr=seqs[slot];
  if(!arr.length){ box.innerHTML='<div class="empty">画像が未選択です（複数枚を順番に追加できます）</div>'; return; }
  box.innerHTML=arr.map((u,i)=>
    '<div class="thumb"><span class="no">'+(i+1)+'</span>'+
    '<button class="rm" data-slot="'+slot+'" data-i="'+i+'" title="削除">×</button>'+
    '<img src="'+u+'"></div>').join("");
}
async function handleSeq(slot, input){
  const files=Array.from(input.files||[]);
  input.value="";   // 同じ画像を再度選べるようにクリア
  for(const f of files){
    const url=await fileToDataURL(f, 1600);
    if(url) seqs[slot].push(url);
  }
  renderThumbs(slot);
}
// サムネイルの削除ボタン
document.addEventListener("click", e=>{
  const b=e.target.closest(".rm"); if(!b) return;
  seqs[b.dataset.slot].splice(+b.dataset.i, 1);
  renderThumbs(b.dataset.slot);
});

SEQS.forEach(slot=>{
  document.getElementById("file_"+slot).addEventListener("change", e=>handleSeq(slot, e.target));
  renderThumbs(slot);
});
TARGETS.forEach(slot=>{
  document.getElementById("file_"+slot).addEventListener("change", e=>handleSingle(slot, e.target));
});

document.getElementById("run").onclick=async()=>{
  const sequences={}; SEQS.forEach(s=>{ if(seqs[s].length) sequences[s]=seqs[s]; });
  const targets={};   TARGETS.forEach(s=>{ if(single[s]) targets[s]=single[s]; });
  const total=Object.values(sequences).reduce((a,v)=>a+v.length,0)+Object.keys(targets).length;
  if(total===0){ alert("少なくとも 1 枚の画像が必要です。"); return; }
  const status=document.getElementById("status");
  status.textContent="解析中... しばらくお待ちください。";
  const payload={
    sequences, targets,
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
    # 単一画像（術後イメージ）。プレビュー 1 枚。
    return f"""<div class="slot">
  <h3>{label}</h3>
  <img class="preview" id="img_{slot}" alt="{label}">
  <div class="row">
    <label class="btn primary addbtn" for="file_{slot}">＋ 画像を追加</label>
    <input type="file" id="file_{slot}" accept="image/*" style="display:none">
  </div>
</div>"""


def _seq_html(slot: str, label: str) -> str:
    # 評価用シーケンス。複数枚をサムネイルでプレビューし、順序つきで保持。
    return f"""<div class="slot">
  <h3>{label}</h3>
  <div class="thumbs" id="thumbs_{slot}"></div>
  <div class="row">
    <label class="btn primary addbtn" for="file_{slot}">＋ 画像を追加（複数可）</label>
    <input type="file" id="file_{slot}" accept="image/*" multiple style="display:none">
  </div>
</div>"""


def render_index() -> str:
    html = INDEX_HTML
    seq_labels = {
        "macro_eval": "マクロ｜顔貌・スマイル（評価用）",
        "micro_eval": "ミクロ｜歯・歯肉（評価用）",
    }
    target_labels = {
        "macro_target": "マクロ｜顔貌・スマイル（術後イメージ）",
        "micro_target": "ミクロ｜歯・歯肉（術後イメージ）",
    }
    for slot, label in seq_labels.items():
        html = html.replace(f"__SEQ_{slot}__", _seq_html(slot, label))
    for slot, label in target_labels.items():
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

        # 評価用シーケンス（複数枚）と術後イメージ（単一）を保存
        sequences = payload.get("sequences", {})   # {macro_eval:[dataURL...], micro_eval:[...]}
        targets = payload.get("targets", {})       # {macro_target:dataURL, micro_target:dataURL}

        kwargs: Dict = {}
        for key in ("macro_eval", "micro_eval"):
            paths = []
            for i, durl in enumerate(sequences.get(key, []) or []):
                saved = _save_data_url(durl, case_dir, f"{key}_{i:02d}")
                if saved:
                    paths.append(saved)
            if paths:
                kwargs[key] = paths
        for key in ("macro_target", "micro_target"):
            durl = targets.get(key)
            if durl:
                saved = _save_data_url(durl, case_dir, key)
                if saved:
                    kwargs[key] = saved

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
