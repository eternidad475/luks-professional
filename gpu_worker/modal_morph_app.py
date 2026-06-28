"""
modal_morph_app.py  —  CaseFlow Studio GPU Morphing Pipeline
═══════════════════════════════════════════════════════════════
Platform : Modal  (modal.com)
GPU      : NVIDIA A10G  24 GB VRAM
Storage  : Cloudflare R2  (S3-compatible, zero egress cost)
Queue    : Upstash Redis  (serverless-friendly REST API)

Local deploy (run on YOUR machine):
  pip install modal
  modal setup                         # browser auth (first time only)
  modal secret create caseflow-secrets ...  # see .env.example
  cd gpu_worker
  modal deploy modal_morph_app.py

After deploy, Modal prints:
  https://<USERNAME>--caseflow-morph-web.modal.run
"""

from __future__ import annotations
import os, uuid, json, tempfile, logging
import modal
from fastapi import FastAPI, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

log = logging.getLogger("caseflow_worker")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ══════════════════════════════════════════════════════════════════════════════
# 1.  Modal App  (define first so image builders can reference it)
# ══════════════════════════════════════════════════════════════════════════════
app     = modal.App("caseflow-morph")
SECRETS = modal.Secret.from_name("caseflow-secrets")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Container Image
#     .run_function() executes Python inside the image at build time —
#     no shell-escaping issues, model weights are baked into the layer cache.
# ══════════════════════════════════════════════════════════════════════════════
def _download_weights():
    """Download SAM2-Small weights into the image (build-time only)."""
    import os, urllib.request
    os.makedirs("/opt/checkpoints", exist_ok=True)

    # SAM 2.1 Small  (~184 MB)
    sam2_url  = ("https://dl.fbaipublicfiles.com/segment_anything_2"
                 "/092824/sam2.1_hiera_small.pt")
    sam2_dest = "/opt/checkpoints/sam2.1_hiera_small.pt"
    if not os.path.exists(sam2_dest):
        print("Downloading SAM2 weights …")
        urllib.request.urlretrieve(sam2_url, sam2_dest)
        print(f"  → {os.path.getsize(sam2_dest)//1024//1024} MB saved")
    print("  → SAM2 ready (interpolation: eased cross-dissolve)")


GPU_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0",
        "libsm6", "libxext6", "libxrender-dev", "git",
        "fonts-noto-cjk",   # Japanese text rendering in PIL
    )
    # PyTorch (CUDA 12.1 build)
    .pip_install(
        "torch==2.3.1", "torchvision==0.18.1",
        index_url="https://download.pytorch.org/whl/cu121",
    )
    # Inference + serving dependencies
    .pip_install(
        "numpy==1.26.4",
        "opencv-python-headless==4.10.0.84",
        "mediapipe==0.10.14",
        "Pillow==10.4.0",
        "scikit-image==0.24.0",
        "ffmpeg-python==0.2.0",
        "boto3==1.35.0",
        "httpx==0.27.0",
        "fastapi[standard]==0.111.1",
        "python-multipart==0.0.9",
    )
    # SAM 2 (pip from GitHub — registers Hydra configs automatically)
    .run_commands(
        "pip install 'git+https://github.com/facebookresearch/segment-anything-2.git'"
    )
    # Bake model weights into image layer (runs _download_weights inside container)
    .run_function(_download_weights)
)


# ══════════════════════════════════════════════════════════════════════════════
# 3.  Cloudflare R2  (private bucket + time-limited presigned GET URLs)
# ══════════════════════════════════════════════════════════════════════════════
def _r2():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["R2_ENDPOINT"],
        aws_access_key_id     = os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"],
        region_name           = "auto",
    )

def r2_put(r2, key: str, data: bytes, ct: str = "application/octet-stream"):
    r2.put_object(Bucket=os.environ["R2_BUCKET"], Key=key, Body=data, ContentType=ct)

def r2_get(r2, key: str) -> bytes:
    return r2.get_object(Bucket=os.environ["R2_BUCKET"], Key=key)["Body"].read()

def r2_signed(r2, key: str, expires: int = 86400) -> str:
    return r2.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["R2_BUCKET"], "Key": key},
        ExpiresIn=expires,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Upstash Redis  (REST — works from any runtime, no TCP connection needed)
# ══════════════════════════════════════════════════════════════════════════════
def _redis_base() -> str:
    return os.environ["UPSTASH_REDIS_REST_URL"].strip().rstrip("/")

def _redis_hdr():
    token = os.environ["UPSTASH_REDIS_REST_TOKEN"].strip()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def redis_set(key: str, val: dict, ttl: int = 7200):
    """URL-path format: POST /set/{key}/{value}?ex={ttl}  (most reliable Upstash API form)."""
    import httpx, urllib.parse
    base    = _redis_base()
    encoded = json.dumps(val, separators=(",", ":"))
    k = urllib.parse.quote(key,     safe="")
    v = urllib.parse.quote(encoded, safe="")
    r = httpx.post(f"{base}/set/{k}/{v}?ex={ttl}",
                   headers=_redis_hdr(), timeout=10)
    log.info(f"redis_set {key}: HTTP {r.status_code} body={r.text[:200]}")
    r.raise_for_status()
    resp = r.json()
    if not isinstance(resp, dict) or resp.get("result") != "OK":
        raise RuntimeError(f"redis SET not OK: {resp}")

def redis_get(key: str) -> dict | None:
    """URL-path format: GET /get/{key}"""
    import httpx, urllib.parse
    base = _redis_base()
    try:
        k = urllib.parse.quote(key, safe="")
        r = httpx.get(f"{base}/get/{k}",
                      headers=_redis_hdr(), timeout=10)
        log.info(f"redis_get {key}: HTTP {r.status_code} body={r.text[:200]}")
        r.raise_for_status()
        resp = r.json()
        raw  = resp.get("result") if isinstance(resp, dict) else None
        return json.loads(raw) if raw else None
    except Exception as e:
        log.error(f"redis_get FAILED {key}: {e}")
        return None

def redis_incr(key: str) -> int:
    """POST /incr/{key} — atomic increment, returns new value."""
    import httpx, urllib.parse
    base = _redis_base()
    k = urllib.parse.quote(key, safe="")
    r = httpx.post(f"{base}/incr/{k}", headers=_redis_hdr(), timeout=10)
    r.raise_for_status()
    return int(r.json().get("result", 0))

def redis_decr(key: str) -> int:
    """POST /decr/{key} — atomic decrement, clamps to 0."""
    import httpx, urllib.parse
    base = _redis_base()
    k = urllib.parse.quote(key, safe="")
    r = httpx.post(f"{base}/decr/{k}", headers=_redis_hdr(), timeout=10)
    r.raise_for_status()
    val = int(r.json().get("result", 0))
    return max(0, val)

def redis_expire(key: str, ttl: int):
    """POST /expire/{key}/{seconds} — set TTL on existing key."""
    import httpx, urllib.parse
    base = _redis_base()
    k = urllib.parse.quote(key, safe="")
    httpx.post(f"{base}/expire/{k}/{ttl}", headers=_redis_hdr(), timeout=10)

# Maximum simultaneous GPU pipeline jobs.
# Each job uses one A10G container. Keep headroom for burst bursts.
_MAX_ACTIVE_GPU = 8
_ACTIVE_KEY     = "system:active_gpu_jobs"


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Dental segmentation
#     Primary  : SAM 2 guided by MediaPipe mouth-ring landmarks
#     Fallback : MediaPipe polygon mask (if no GPU or SAM2 init fails)
# ══════════════════════════════════════════════════════════════════════════════
_MOUTH_RING = [
    61,146,91,181,84,17,314,405,321,375,291,409,
    270,269,267,0,37,39,40,185,
    13,312,311,310,415,308,324,318,402,317,14,87,178,88,95,
    78,191,80,81,82,
]

def dental_mask(img_bgr) -> "np.ndarray":
    """Float32 soft mask [H,W] ∈ [0,1] covering the dental region."""
    import cv2, numpy as np, mediapipe as mp

    h, w = img_bgr.shape[:2]
    rgb   = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1,
        refine_landmarks=True, min_detection_confidence=0.5,
    ) as fm:
        res = fm.process(rgb)
    if not res.multi_face_landmarks:
        raise ValueError("No face detected")

    lms  = res.multi_face_landmarks[0].landmark
    pts  = np.array([[int(lms[i].x * w), int(lms[i].y * h)]
                     for i in _MOUTH_RING], dtype=np.int32)
    cent = pts.mean(axis=0)

    try:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        # Config file is registered by the sam2 package via Hydra
        model = build_sam2(
            "sam2.1_hiera_s.yaml",
            "/opt/checkpoints/sam2.1_hiera_small.pt",
            device=device,
        )
        pred = SAM2ImagePredictor(model)
        pred.set_image(rgb)

        x0, y0 = (pts.min(axis=0) - 28).clip(0)
        x1, y1 = pts.max(axis=0) + 28
        x1, y1 = min(x1, w), min(y1, h)
        box    = np.array([x0, y0, x1, y1], dtype=float)

        masks, _, _ = pred.predict(
            point_coords=cent[None], point_labels=np.array([1]),
            box=box[None], multimask_output=False,
        )
        mask = masks[0].astype(np.float32)
        del model, pred
        torch.cuda.empty_cache()
        log.info("SAM2 mask OK")

    except Exception as e:
        log.warning(f"SAM2 fallback ({e})")
        mask = np.zeros((h, w), np.float32)
        cv2.fillPoly(mask, [pts], 1.0)

    u8 = (mask * 255).astype(np.uint8)
    return cv2.GaussianBlur(u8, (0, 0), sigmaX=10).astype(np.float32) / 255.0


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Color harmonization  (Reinhard 2001 Lab transfer)
# ══════════════════════════════════════════════════════════════════════════════
def color_match(src_bgr, tgt_bgr, mask) -> "np.ndarray":
    import cv2, numpy as np

    def to_lab(x):
        return cv2.cvtColor(x.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)
    def from_lab(x):
        return np.clip(cv2.cvtColor(x, cv2.COLOR_Lab2BGR) * 255, 0, 255).astype(np.uint8)

    sl, tl = to_lab(src_bgr), to_lab(tgt_bgr)
    for ch in range(3):
        sv = sl[:, :, ch][mask > 0.5]
        tv = tl[:, :, ch][mask > 0.5]
        if len(sv) < 10:
            continue
        adjusted = (sl[:, :, ch] - sv.mean()) * \
                   (tv.std() + 1e-6) / (sv.std() + 1e-6) + tv.mean()
        sl[:, :, ch] = np.where(mask > 0.5, adjusted, sl[:, :, ch])
    return from_lab(sl)


# ══════════════════════════════════════════════════════════════════════════════
# 7.  Face alignment  (homography via outer-face MediaPipe landmarks)
# ══════════════════════════════════════════════════════════════════════════════
_FACE_IDX = [
    10,338,297,332,284,251,389,356,454,323,361,288,
    397,365,379,378,400,377,152,148,176,149,150,136,
    172,58,132,93,234,127,162,21,54,103,67,109,
]

def align_to_master(src, master) -> "np.ndarray":
    import cv2, numpy as np, mediapipe as mp

    h, w = master.shape[:2]

    def pts(img):
        with mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True, max_num_faces=1,
            min_detection_confidence=0.5,
        ) as fm:
            res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks:
            return None
        lms = res.multi_face_landmarks[0].landmark
        ih, iw = img.shape[:2]
        return np.array([[lms[i].x * iw, lms[i].y * ih]
                         for i in _FACE_IDX], dtype=np.float32)

    sp, mp_ = pts(src), pts(master)
    if sp is None or mp_ is None:
        return cv2.resize(src, (w, h))
    H, _ = cv2.findHomography(sp, mp_, cv2.RANSAC, 5.0)
    return cv2.warpPerspective(src, H, (w, h)) if H is not None \
           else cv2.resize(src, (w, h))


# ══════════════════════════════════════════════════════════════════════════════
# 8.  Frame interpolation  (RAFT optical flow → forward+backward warp + blend)
# ══════════════════════════════════════════════════════════════════════════════
_RAFT = None

def _get_raft():
    global _RAFT
    if _RAFT is None:
        import torch
        from torchvision.models.optical_flow import raft_large, Raft_Large_Weights
        _RAFT = raft_large(weights=Raft_Large_Weights.DEFAULT).cuda().eval()
        log.info("RAFT loaded")
    return _RAFT

def _warp(img, flow):
    import cv2, numpy as np
    h, w   = img.shape[:2]
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    return cv2.remap(img,
                     np.clip(gx + flow[0], 0, w - 1),
                     np.clip(gy + flow[1], 0, h - 1),
                     cv2.INTER_LANCZOS4)

def _ease(t: float) -> float:
    return 4 * t**3 if t < 0.5 else 1 - (-2*t + 2)**3 / 2

def _pad8(img):
    """Pad image so H and W are divisible by 8 (RAFT requirement). Returns (padded, orig_h, orig_w)."""
    import numpy as np
    h, w = img.shape[:2]
    ph = (8 - h % 8) % 8
    pw = (8 - w % 8) % 8
    if ph == 0 and pw == 0:
        return img, h, w
    return np.pad(img, ((0, ph), (0, pw), (0, 0)), mode="reflect"), h, w

def interp_segment(a_bgr, b_bgr, n: int, *,
                   warp_only: bool = False,
                   motion_smooth: str = "normal",
                   dental_pres: str = "high") -> list:
    """Bidirectional Farneback flow morph — configurable quality and dissolve mode.

    warp_only=True   : pure mesh-warp cutover at midpoint; no alpha blending.
                       Eliminates cross-dissolve and ghosting entirely.
    warp_only=False  : warped frames are cross-faded for a softer transition.
    motion_smooth    : "low" / "normal" / "high" — controls Farneback window size
                       and iteration count.
    dental_pres      : "low" / "normal" / "high" — clamps max flow displacement
                       as a fraction of image width, limiting over-warping of
                       dental structures.
    """
    import numpy as np
    import cv2

    H, W = a_bgr.shape[:2]

    # Farneback parameter sets
    _FB = {
        "low":    dict(pyr_scale=0.5, levels=3, winsize=11, iterations=3, poly_n=5, poly_sigma=1.1),
        "normal": dict(pyr_scale=0.5, levels=5, winsize=21, iterations=5, poly_n=7, poly_sigma=1.5),
        "high":   dict(pyr_scale=0.5, levels=6, winsize=31, iterations=7, poly_n=7, poly_sigma=1.5),
    }
    fb = _FB.get(motion_smooth, _FB["normal"])

    # Max flow displacement as fraction of image width (dental preservation)
    _MAX_DISP = {"low": 0.6, "normal": 0.4, "high": 0.25}
    max_disp = _MAX_DISP.get(dental_pres, 0.25) * W

    # Compute flow on a downscaled copy for speed; scale vectors back up
    scale = min(1.0, 512 / max(H, W))
    if scale < 1.0:
        a_small = cv2.resize(a_bgr, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
        b_small = cv2.resize(b_bgr, (int(W * scale), int(H * scale)), interpolation=cv2.INTER_AREA)
    else:
        a_small, b_small = a_bgr, b_bgr

    a_gray = cv2.cvtColor(a_small, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(b_small, cv2.COLOR_BGR2GRAY)

    flow_ab = cv2.calcOpticalFlowFarneback(a_gray, b_gray, None, flags=0, **fb)
    flow_ba = cv2.calcOpticalFlowFarneback(b_gray, a_gray, None, flags=0, **fb)

    if scale < 1.0:
        flow_ab = cv2.resize(flow_ab, (W, H), interpolation=cv2.INTER_LINEAR) / scale
        flow_ba = cv2.resize(flow_ba, (W, H), interpolation=cv2.INTER_LINEAR) / scale

    # Clamp flow magnitude to preserve dental/lip structures from over-warping
    for flow in (flow_ab, flow_ba):
        mag = np.linalg.norm(flow, axis=-1, keepdims=True)
        scale_vec = np.where(mag > max_disp, max_disp / (mag + 1e-6), 1.0)
        flow[...] *= scale_vec

    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float32),
                                  np.arange(H, dtype=np.float32))

    frames = []
    for i in range(n):
        t = _ease((i + 1) / (n + 1))

        # Warp A forward by t * flow_ab
        map_xa = (grid_x + t * flow_ab[..., 0]).clip(0, W - 1)
        map_ya = (grid_y + t * flow_ab[..., 1]).clip(0, H - 1)
        warped_a = cv2.remap(a_bgr, map_xa, map_ya,
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

        # Warp B backward by (1-t) * flow_ba
        map_xb = (grid_x + (1 - t) * flow_ba[..., 0]).clip(0, W - 1)
        map_yb = (grid_y + (1 - t) * flow_ba[..., 1]).clip(0, H - 1)
        warped_b = cv2.remap(b_bgr, map_xb, map_yb,
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

        if warp_only:
            # Pure warp: sharp cutover at midpoint — no alpha blend, no ghosting
            frame = warped_a if t < 0.5 else warped_b
        else:
            frame = (warped_a.astype(np.float32) * (1 - t) +
                     warped_b.astype(np.float32) * t).clip(0, 255).astype(np.uint8)

        frames.append(frame)

    return frames


# ══════════════════════════════════════════════════════════════════════════════
# 9.  Caption helper  — clinical stage labels + treatment overlay using PIL
# ══════════════════════════════════════════════════════════════════════════════
_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
]

def add_caption(frame_bgr, stage: str, sub: str = "") -> "np.ndarray":
    """Overlay a stage label and optional sub-line at the bottom of a frame."""
    import numpy as np, cv2
    from PIL import Image, ImageDraw, ImageFont

    img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).convert("RGBA")
    W, H = img.size
    bar_h = max(60, int(H * 0.11))

    # Semi-transparent black bottom bar
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    from PIL import ImageDraw as ID
    od = ID.Draw(overlay)
    od.rectangle([(0, H - bar_h), (W, H)], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # Font sizes proportional to frame width
    sz_main = max(28, W // 26)
    sz_sub  = max(20, W // 38)
    font_main = font_sub = ImageFont.load_default()
    for fp in _FONT_PATHS:
        try:
            font_main = ImageFont.truetype(fp, sz_main)
            font_sub  = ImageFont.truetype(fp, sz_sub)
            break
        except Exception:
            pass

    cx = W // 2
    if sub:
        draw.text((cx, H - bar_h + bar_h // 3), stage, font=font_main,
                  fill=(255, 255, 255, 255), anchor="mm")
        draw.text((cx, H - bar_h // 5), sub, font=font_sub,
                  fill=(210, 210, 210, 255), anchor="mm")
    else:
        draw.text((cx, H - bar_h // 2), stage, font=font_main,
                  fill=(255, 255, 255, 255), anchor="mm")

    result = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    return result


def _auto_stage_labels(n: int) -> list[str]:
    if n == 1:  return ["治療記録"]
    if n == 2:  return ["治療前", "治療後"]
    if n == 3:  return ["治療前", "経過観察", "治療後"]
    return ["治療前"] + [f"治療中 {chr(0x2460 + i)}" for i in range(n - 2)] + ["治療後"]


# ══════════════════════════════════════════════════════════════════════════════
# 10. GPU Function  —  the clinical-record video pipeline
# ══════════════════════════════════════════════════════════════════════════════
def _apply_output_ratio(frames: list, ratio_str: str) -> tuple:
    """Center-crop all frames to the requested aspect ratio (w:h).

    Returns (cropped_frames, out_w, out_h). Dimensions are forced even for H.264.
    If ratio_str is empty or 'original', frames are returned unchanged.
    """
    import cv2, numpy as np
    if not frames or not ratio_str or ratio_str == "original":
        h0, w0 = frames[0].shape[:2]
        return frames, w0 - (w0 % 2), h0 - (h0 % 2)

    parts = ratio_str.split(":")
    if len(parts) != 2:
        h0, w0 = frames[0].shape[:2]
        return frames, w0 - (w0 % 2), h0 - (h0 % 2)

    rw, rh = float(parts[0]), float(parts[1])
    target_ar = rw / rh
    H, W = frames[0].shape[:2]
    src_ar = W / H

    if abs(src_ar - target_ar) < 0.005:
        return frames, W - (W % 2), H - (H % 2)

    if src_ar > target_ar:
        # source wider than target — crop left/right edges
        new_w = int(round(H * target_ar))
        new_w = new_w - (new_w % 2)
        x0 = (W - new_w) // 2
        out = [fr[:, x0:x0 + new_w] for fr in frames]
        return out, new_w, H - (H % 2)
    else:
        # source taller than target — crop top/bottom edges
        new_h = int(round(W / target_ar))
        new_h = new_h - (new_h % 2)
        y0 = (H - new_h) // 2
        out = [fr[y0:y0 + new_h, :] for fr in frames]
        return out, W - (W % 2), new_h


@app.function(
    image          = GPU_IMAGE,
    gpu            = "A10G",
    secrets        = [SECRETS],
    timeout        = 600,       # 10 min ceiling per job
    memory         = 32768,
    max_containers = 10,        # cap GPU spend; jobs beyond this queue inside Modal
)
def run_pipeline(job_id: str, frame_keys: list[str],
                 duration_ms: int, fps: int,
                 treatment_name: str = "",
                 treatment_duration: str = "",
                 patient_info: str = "",
                 output_ratio: str = "9:16",
                 show_caption: bool = False,
                 seamless_mode: bool = False,
                 warp_only: bool = False,
                 no_dissolve: bool = False,
                 motion_smooth: str = "normal",
                 dental_pres: str = "high",
                 keyframe_count: int = 3):
    import cv2, numpy as np
    import ffmpeg as ff

    r2 = _r2()

    def status(s: str, p: int = 0, url: str = ""):
        redis_set(f"job:{job_id}", {"status": s, "progress": p, "resultUrl": url})
        log.info(f"[{job_id}] {s} {p}%")

    try:
        # A ── Download clinical photos from R2 (must stay unmodified) ────
        status("downloading", 2)
        raw = []
        for key in frame_keys:
            arr = np.frombuffer(r2_get(r2, key), np.uint8)
            raw.append(cv2.imdecode(arr, cv2.IMREAD_COLOR))

        H, W = raw[-1].shape[:2]
        log.info(f"[{job_id}] {len(raw)} clinical photos · canvas {W}×{H}")

        # B ── Scale all photos to match the last photo's dimensions ─────
        # We scale (not letterbox) to keep the full-bleed look.
        # The last photo's dimensions define the canvas; all others are
        # resized to match so the video encoder gets consistent frame sizes.
        status("segmenting", 10)

        frames = []
        for fr in raw:
            if fr.shape[:2] == (H, W):
                frames.append(fr.copy())
            else:
                frames.append(cv2.resize(fr, (W, H), interpolation=cv2.INTER_LANCZOS4))
        log.info(f"[{job_id}] {len(frames)} frames scaled to {W}×{H}")

        # C ── Build video: hold each key frame + GPU-generated tween frames
        # Like clay-animation: the actual clinical photos are the key frames,
        # held on screen; the GPU generates smooth in-between frames only for
        # the transitions between consecutive photos.
        status("interpolating", 36)

        n        = len(frames)
        seg_ms   = duration_ms / max(1, n - 1)   # time per segment
        hold_n   = max(2, round(seg_ms * 0.55 / 1000 * fps))   # 55% = hold key frame
        trans_n  = max(1, round(seg_ms * 0.45 / 1000 * fps))   # 45% = tween (zoom-dissolve)

        log.info(f"[{job_id}] hold={hold_n}f  tween={trans_n}f  per segment")

        # Caption overlay — only when user explicitly enables the toggle in the Prompt Board
        stage_labels = _auto_stage_labels(n)
        sub_line = "  ·  ".join(filter(None, [treatment_name, treatment_duration, patient_info]))
        use_caption = show_caption and bool(treatment_name or treatment_duration or patient_info)
        log.info(f"[{job_id}] caption={'on' if use_caption else 'off'}  sub='{sub_line[:60]}'")

        # Resolve effective rendering flags (seamless_mode enables all strict modes)
        eff_warp_only  = seamless_mode or warp_only or no_dissolve
        eff_smooth     = motion_smooth if motion_smooth in ("low", "normal", "high") else "normal"
        eff_dental     = dental_pres   if dental_pres   in ("low", "normal", "high") else "high"
        log.info(f"[{job_id}] seamless={seamless_mode} warp_only={eff_warp_only} "
                 f"smooth={eff_smooth} dental={eff_dental} kf_count={keyframe_count}")

        all_frames = []
        for i, fr in enumerate(frames):
            status("interpolating", 36 + int(i / n * 46))
            fr_display = add_caption(fr, stage_labels[i], sub_line) if use_caption else fr
            all_frames.extend([fr_display] * hold_n)
            if i < n - 1:
                all_frames.extend(interp_segment(fr, frames[i + 1], trans_n,
                                                 warp_only=eff_warp_only,
                                                 motion_smooth=eff_smooth,
                                                 dental_pres=eff_dental))

        log.info(f"[{job_id}] {len(all_frames)} total frames → {len(all_frames)/fps:.1f}s")

        # C.5 ── Crop frames to requested SNS output ratio ─────────────────
        all_frames, W, H = _apply_output_ratio(all_frames, output_ratio)
        log.info(f"[{job_id}] output ratio '{output_ratio}' → {W}×{H}")

        # D ── Encode MP4 ──────────────────────────────────────────────────
        status("encoding", 82)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            out_path = f.name

        proc = (
            ff.input("pipe:", format="rawvideo", pix_fmt="bgr24",
                     s=f"{W}x{H}", r=fps, framerate=fps)
            .output(out_path,
                    vcodec="libx264", pix_fmt="yuv420p",
                    crf=16, preset="fast", movflags="+faststart",
                    **{"profile:v": "high", "level": "4.1"})
            .overwrite_output()
            .run_async(pipe_stdin=True, quiet=True)
        )
        for fr in all_frames:
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
        proc.wait()

        # E ── Upload result to R2 ─────────────────────────────────────────
        status("uploading", 95)
        result_key = f"results/{job_id}/morph.mp4"
        with open(out_path, "rb") as f:
            r2_put(r2, result_key, f.read(), "video/mp4")
        os.unlink(out_path)

        url = r2_signed(r2, result_key, expires=86400)   # valid 24 h
        status("done", 100, url)
        log.info(f"[{job_id}] complete → {url[:80]}…")

    except Exception as e:
        log.exception(f"[{job_id}] FATAL")
        redis_set(f"job:{job_id}", {
            "status": "error", "progress": 0,
            "resultUrl": "", "error": str(e)[:400],
        })

    finally:
        # Always release the active-job slot so capacity is never leaked
        try:
            redis_decr(_ACTIVE_KEY)
        except Exception as ex:
            log.warning(f"[{job_id}] failed to decrement active counter: {ex}")


# ══════════════════════════════════════════════════════════════════════════════
# 10. FastAPI web endpoints  (served by Modal's ASGI runner)
#
#     POST /api/morph/submit  → upload frames to R2, spawn GPU job, return jobId
#     GET  /api/morph/status  → read Upstash Redis, return {status,progress,url}
#     GET  /health            → liveness probe
# ══════════════════════════════════════════════════════════════════════════════
web_app = FastAPI(title="CaseFlow Morph API", version="1.0.0")
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://caseflow-studio.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods     = ["GET", "POST", "OPTIONS"],
    allow_headers     = ["*"],
    allow_credentials = False,
)


@web_app.post("/api/morph/submit", status_code=202)
async def submit(
    frame             : list[UploadFile] = File(...),
    durationMs        : int              = Form(4000),
    fps               : int              = Form(30),
    treatmentName     : str              = Form(""),
    treatmentDuration : str              = Form(""),
    patientInfo       : str              = Form(""),
    outputRatio       : str              = Form("9:16"),
    showCaption       : str              = Form("0"),
    seamlessMode      : str              = Form("0"),
    aiKeyframes       : str              = Form("0"),
    keyframeCount     : int              = Form(3),
    warpOnly          : str              = Form("0"),
    noDissolve        : str              = Form("0"),
    motionSmooth      : str              = Form("normal"),
    dentalPres        : str              = Form("high"),
):
    job_id = str(uuid.uuid4())
    r2     = _r2()

    # ── Capacity gate: reject early if too many GPU jobs are active ──────────
    # This prevents Modal from returning its own 429/500 under load and gives
    # the client a clean 503 + Retry-After header it can handle gracefully.
    try:
        active = redis_incr(_ACTIVE_KEY)
        redis_expire(_ACTIVE_KEY, 3600)   # safety TTL in case of crash
        log.info(f"[{job_id}] active GPU jobs after incr: {active}")
        if active > _MAX_ACTIVE_GPU:
            redis_decr(_ACTIVE_KEY)
            retry_after = 30
            log.warning(f"[{job_id}] capacity exceeded ({active} > {_MAX_ACTIVE_GPU}) — 503")
            return JSONResponse(
                {"error": "サーバーが混雑しています。しばらくお待ちください。",
                 "retry_after": retry_after,
                 "active": active, "max": _MAX_ACTIVE_GPU},
                status_code=503,
                headers={"Retry-After": str(retry_after)},
            )
    except Exception as cap_err:
        log.warning(f"[{job_id}] capacity check failed ({cap_err}) — proceeding anyway")

    frame_keys = []
    for i, f in enumerate(frame):
        data = await f.read()
        key  = f"uploads/{job_id}/frame_{i:03d}.jpg"
        r2_put(r2, key, data, "image/jpeg")
        frame_keys.append(key)
        log.info(f"[{job_id}] uploaded frame {i}")

    try:
        redis_set(f"job:{job_id}", {"status": "queued", "progress": 1, "resultUrl": ""})
    except Exception as e:
        # Decrement counter since we're not spawning
        try: redis_decr(_ACTIVE_KEY)
        except: pass
        log.error(f"[{job_id}] redis_set queued FAILED: {e}")
        return JSONResponse({"error": f"Redis unavailable: {str(e)[:200]}"}, status_code=503)

    # Non-blocking spawn — returns immediately, GPU runs in background
    run_pipeline.spawn(
        job_id, frame_keys, durationMs, fps,
        treatmentName, treatmentDuration, patientInfo, outputRatio,
        showCaption  == "1",
        seamlessMode == "1",
        warpOnly     == "1",
        noDissolve   == "1",
        motionSmooth,
        dentalPres,
        keyframeCount,
    )

    return JSONResponse({"jobId": job_id})


@web_app.get("/api/morph/status")
async def job_status(jobId: str = Query(...)):
    data = redis_get(f"job:{jobId}")
    if data is None:
        return JSONResponse({"status": "unknown", "progress": 0,
                             "resultUrl": "", "error": "job not found"},
                            status_code=404)
    return JSONResponse(data)


@web_app.get("/api/morph/download")
async def download(jobId: str):
    """Proxy the finished MP4 through Modal so browsers avoid R2 CORS restrictions."""
    import httpx
    from fastapi.responses import StreamingResponse
    data = redis_get(f"job:{jobId}")
    if data is None:
        return JSONResponse({"error": "job not found"}, status_code=404)
    if data.get("status") != "done" or not data.get("resultUrl"):
        return JSONResponse({"error": "job not ready", "status": data.get("status")}, status_code=409)
    url = data["resultUrl"]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(url)
        if r.status_code != 200:
            return JSONResponse({"error": f"R2 fetch failed: {r.status_code}"}, status_code=502)
        video_bytes = r.content
    return StreamingResponse(
        iter([video_bytes]),
        media_type="video/mp4",
        headers={"Content-Disposition": 'attachment; filename="caseflow_ai_morph.mp4"'},
    )


@web_app.get("/health")
async def health():
    redis_ok = False
    redis_err = ""
    try:
        redis_set("__health__", {"ok": True}, ttl=60)
        data = redis_get("__health__")
        redis_ok = isinstance(data, dict) and data.get("ok") is True
    except Exception as e:
        redis_err = str(e)[:200]
    return {"ok": True, "redis": redis_ok, "redis_err": redis_err,
            "service": "caseflow-morph",
            "upstash_url": _redis_base()[:40] + "…"}


@web_app.get("/debug")
async def debug():
    """Browser-accessible Redis connectivity test — shows raw Upstash responses."""
    import httpx, urllib.parse, traceback
    steps = []
    try:
        base = _redis_base()
        hdr  = _redis_hdr()
        steps.append(f"url={base[:55]}…")

        k = urllib.parse.quote("__dbg__", safe="")
        v = urllib.parse.quote("hello123", safe="")
        r1 = httpx.post(f"{base}/set/{k}/{v}?ex=120", headers=hdr, timeout=10)
        steps.append(f"SET HTTP {r1.status_code}: {r1.text[:150]}")

        r2 = httpx.get(f"{base}/get/{k}", headers=hdr, timeout=10)
        steps.append(f"GET HTTP {r2.status_code}: {r2.text[:150]}")

        ok = r2.json().get("result") == "hello123"
        return {"redis": "ok" if ok else "mismatch", "steps": steps}
    except Exception as e:
        steps.append(f"ERROR: {e}")
        return {"redis": "error", "steps": steps,
                "trace": traceback.format_exc()[-600:]}


# ── Wire FastAPI into Modal ───────────────────────────────────────────────────
@app.function(
    image                  = GPU_IMAGE,
    secrets                = [SECRETS],
    min_containers         = 1,    # 1 warm instance — eliminates cold start
    allow_concurrent_inputs= 50,   # async FastAPI handles 50 concurrent HTTP requests per container
)
@modal.asgi_app()
def web():
    return web_app
