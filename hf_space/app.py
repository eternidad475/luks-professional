import base64
import io
import math
import os
import re
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio.v2 as imageio
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
STUDIO_DIR = BASE_DIR / "studio"
# 生成動画は一時保存（環境変数で書き込み可能な場所に変更可能）
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", BASE_DIR / "outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024

ASPECT_SIZES = {
    "9:16": (720, 1280),
    "4:5": (720, 900),
    "1:1": (900, 900),
    "16:9": (1280, 720),
}


def cleanup_outputs(max_age_seconds=3600):
    now = time.time()
    for path in OUTPUT_DIR.glob("*"):
        try:
            if path.is_file() and now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
        except Exception:
            pass


@app.route("/")
def root():
    return redirect("/studio/")


@app.route("/studio/")
def studio_index():
    return send_file(STUDIO_DIR / "index.html")


@app.route("/studio/<path:filename>")
def studio_files(filename):
    return send_from_directory(STUDIO_DIR, filename)


@app.route("/outputs/<path:filename>")
def output_files(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=False)


def decode_data_url(data_url: str) -> Image.Image:
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    data = base64.b64decode(data_url)
    return Image.open(io.BytesIO(data)).convert("RGB")


def cover_resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    resized = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return resized.crop((left, top, left + tw, top + th))


def ease_in_out(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def zoom_center(img: Image.Image, zoom: float) -> Image.Image:
    if abs(zoom - 1.0) < 0.001:
        return img
    w, h = img.size
    nw, nh = int(w * zoom), int(h * zoom)
    z = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return z.crop((left, top, left + w, top + h))


def mouth_weighted_warp(img: Image.Image, phase: float, amount: float, mouth_v: float = 0.58, strips: int = 54) -> Image.Image:
    if amount <= 0:
        return img
    w, h = img.size
    out = Image.new("RGB", (w, h), (13, 10, 24))
    for i in range(strips):
        v0 = i / strips
        v1 = (i + 1) / strips
        vc = (v0 + v1) / 2.0
        y0 = int(v0 * h)
        y1 = int(v1 * h) + 1
        env = math.exp(-(((vc - mouth_v) / 0.24) ** 2))
        wave = amount * env * (
            math.sin(vc * math.pi * 3.0 + phase) * 0.65
            + math.sin(vc * math.pi * 6.0 + phase * 1.7) * 0.35
        )
        squeeze = 1.0 - min(0.055, 0.004 * amount) * env
        strip = img.crop((0, y0, w, min(h, y1)))
        sw = max(2, int(w * squeeze))
        strip = strip.resize((sw, strip.height), Image.LANCZOS)
        x = int((w - sw) / 2 + wave)
        out.paste(strip, (x, y0))
    return out


def load_font(size: int, bold: bool = False):
    # 日本語ラベルを描画するため CJK フォントを優先（無ければ Latin にフォールバック）。
    candidates = [
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def hex_to_rgb(hex_color: str, fallback=(124, 92, 255)):
    if not isinstance(hex_color, str):
        return fallback
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", hex_color.strip())
    if not m:
        return fallback
    v = m.group(1)
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))


def rounded(draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except Exception:
        draw.rectangle(xy, fill=fill)


def draw_template(frame: Image.Image, label: str, template: str, title: str, colors: list[str], index: int, total: int) -> Image.Image:
    img = frame.convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    c1 = hex_to_rgb(colors[0] if colors else "#7c5cff")
    c2 = hex_to_rgb(colors[1] if len(colors) > 1 else "#ff9fd6")
    font_tag = load_font(max(18, w // 38), bold=True)
    font_small = load_font(max(14, w // 58), bold=False)
    font_title = load_font(max(22, w // 30), bold=True)
    label = (label or f"Frame {index + 1}").strip()[:24]
    title = (title or "Smile Morph Studio").strip()[:36]

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay, "RGBA")
    for y in range(int(h * 0.22)):
        od.line([(0, y), (w, y)], fill=(0, 0, 0, int(82 * (1 - y / (h * 0.22)))))
    for y in range(int(h * 0.78), h):
        od.line([(0, y), (w, y)], fill=(0, 0, 0, int(96 * ((y - h * 0.78) / (h * 0.22)))))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img, "RGBA")

    if template in ("aesthetic", "smile"):
        aura = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ad = ImageDraw.Draw(aura, "RGBA")
        ad.ellipse((w * 0.04, h * 0.66, w * 0.96, h * 1.18), fill=(*c2, 42))
        aura = aura.filter(ImageFilter.GaussianBlur(max(18, w // 24)))
        img = Image.alpha_composite(img, aura)
        draw = ImageDraw.Draw(img, "RGBA")

    pad = max(24, w // 30)
    tag_h = max(42, h // 18)
    tag_w = int(w * 0.32)
    rounded(draw, (pad, pad, pad + tag_w, pad + tag_h), tag_h // 2, (255, 255, 255, 190))
    draw.text((pad + tag_h * 0.35, pad + tag_h * 0.22), label, fill=(32, 27, 53, 255), font=font_tag)

    draw.text((pad, h - pad - tag_h * 1.22), title, fill=(255, 255, 255, 232), font=font_title)

    if template == "timeline":
        dot_y = h - pad
        available = w - pad * 2
        step = available / max(1, total - 1)
        for i in range(total):
            x = pad + step * i
            r = max(5, w // 90)
            fill = (255, 255, 255, 235) if i <= index else (255, 255, 255, 92)
            draw.ellipse((x - r, dot_y - r, x + r, dot_y + r), fill=fill)

    if template == "beforeafter":
        draw.text((pad, h - pad - tag_h * 0.48), "Before / Progress / After", fill=(255, 255, 255, 178), font=font_small)

    if template == "smile":
        y = int(h * 0.58)
        x0, x1 = int(w * 0.22), int(w * 0.78)
        points = []
        for i in range(70):
            t = i / 69
            x = x0 + (x1 - x0) * t
            yy = y + math.sin(t * math.pi) * int(h * 0.045)
            points.append((x, yy))
        draw.line(points, fill=(255, 255, 255, 120), width=max(2, w // 180))

    wm = "Smile Morph Studio / Simulation tool"
    draw.text((w - pad - int(w * 0.34), h - pad - max(14, h // 62)), wm, fill=(255, 255, 255, 160), font=font_small)
    return img.convert("RGB")


def transition_frame(img_a: Image.Image, img_b: Image.Image, t: float, mouth_v: float, warp_strength: float) -> Image.Image:
    e = ease_in_out(t)
    phase = e * math.pi * 2
    warp = warp_strength * math.sin(math.pi * e)
    a = zoom_center(img_a, 1.0 + 0.012 * e)
    b = zoom_center(img_b, 1.012 - 0.012 * e)
    a = mouth_weighted_warp(a, phase, warp, mouth_v=mouth_v)
    b = mouth_weighted_warp(b, phase + math.pi, warp * 0.92, mouth_v=mouth_v)
    return Image.blend(a, b, e)


@app.route("/api/morph_video", methods=["POST"])
def morph_video():
    cleanup_outputs()
    try:
        payload = request.get_json(force=True)
        images = payload.get("images", [])[:10]
        labels = payload.get("labels", [])[: len(images)]
        if len(images) < 2:
            return jsonify(ok=False, error="画像を2枚以上追加してください。"), 400

        aspect = payload.get("aspect", "9:16")
        size = ASPECT_SIZES.get(aspect, ASPECT_SIZES["9:16"])
        fps = max(12, min(int(payload.get("fps", 24)), 30))
        transition = max(0.55, min(float(payload.get("transition", 1.6)), 2.6))
        hold = max(0.0, min(float(payload.get("hold", 0.35)), 0.8))
        template = payload.get("template", "minimal")
        title = payload.get("title", "")
        colors = payload.get("colors", ["#7c5cff", "#ff9fd6"])
        mouth_v = max(0.40, min(float(payload.get("mouth_v", 0.58)), 0.78))
        warp_strength = max(0.0, min(float(payload.get("warp_strength", 10.0)), 18.0))

        frames_base = [cover_resize(decode_data_url(x), size) for x in images]
        total = len(frames_base)
        trans_frames = max(3, int(fps * transition))
        hold_frames = int(fps * hold)

        out_name = f"smile_morph_{uuid.uuid4().hex[:10]}.mp4"
        out_path = OUTPUT_DIR / out_name
        writer = imageio.get_writer(str(out_path), fps=fps, codec="libx264", quality=8, macro_block_size=16, pixelformat="yuv420p")
        try:
            for i in range(total):
                label = labels[i] if i < len(labels) else f"Frame {i + 1}"
                for _ in range(hold_frames):
                    frame = draw_template(frames_base[i], label, template, title, colors, i, total)
                    writer.append_data(np.asarray(frame))

                if i < total - 1:
                    for f in range(trans_frames):
                        t = (f + 1) / trans_frames
                        frame = transition_frame(frames_base[i], frames_base[i + 1], t, mouth_v, warp_strength)
                        label_index = i if t < 0.5 else i + 1
                        label = labels[label_index] if label_index < len(labels) else f"Frame {label_index + 1}"
                        frame = draw_template(frame, label, template, title, colors, label_index, total)
                        writer.append_data(np.asarray(frame))

            for _ in range(max(hold_frames, int(fps * 0.4))):
                label = labels[-1] if labels else "After"
                frame = draw_template(frames_base[-1], label, template, title, colors, total - 1, total)
                writer.append_data(np.asarray(frame))
        finally:
            writer.close()

        return jsonify(ok=True, video_url=f"/outputs/{out_name}")

    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
