"""
modal_morph_app.py  —  CaseFlow Studio GPU Morphing Pipeline
═══════════════════════════════════════════════════════════════
Platform : Modal  (modal.com)
GPU      : NVIDIA A10G  24 GB VRAM
Storage  : Cloudflare R2  (S3-compatible, zero egress cost)
Queue    : Upstash Redis  (job status / progress)

Deploy:
  pip install modal
  modal secret create caseflow-secrets  \  # see .env.example
  modal deploy modal_morph_app.py

Web endpoint URL after deploy:
  https://<your-modal-username>--caseflow-morph-web.modal.run
"""

from __future__ import annotations
import os, uuid, json, math, tempfile, logging, time
from pathlib import Path
import modal

log = logging.getLogger("caseflow_worker")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ══════════════════════════════════════════════════════════════════════════════
# 1.  Container Image
#     Built once, cached in Modal's image registry.
#     SAM2 weights (~184 MB) are baked into the image layer — no cold-start
#     download penalty after the first build.
# ══════════════════════════════════════════════════════════════════════════════
GPU_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0",
        "libsm6", "libxext6", "libxrender-dev", "git",
    )
    .pip_install(
        "torch==2.3.1", "torchvision==0.18.1",
        index_url="https://download.pytorch.org/whl/cu121",
    )
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
    # SAM 2 (Facebook Research)
    .run_commands(
        "pip install 'git+https://github.com/facebookresearch/segment-anything-2.git'"
    )
    # Download SAM 2 Small weights at image-build time (cached forever)
    .run_commands(
        "mkdir -p /opt/checkpoints",
        'python -c "'
        "import urllib.request; "
        "url='https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt'; "
        "urllib.request.urlretrieve(url, '/opt/checkpoints/sam2.1_hiera_small.pt'); "
        'print(\'SAM2 checkpoint ready\')"',
    )
)

# ── App + secrets ─────────────────────────────────────────────────────────────
app     = modal.App("caseflow-morph")
SECRETS = modal.Secret.from_name("caseflow-secrets")   # created via `modal secret create`


# ══════════════════════════════════════════════════════════════════════════════
# 2.  Cloudflare R2 helper  (private bucket + presigned GET URLs)
# ══════════════════════════════════════════════════════════════════════════════
def make_r2():
    import boto3
    return boto3.client(
        "s3",
        endpoint_url          = os.environ["R2_ENDPOINT"],
        aws_access_key_id     = os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key = os.environ["R2_SECRET_ACCESS_KEY"],
        region_name           = "auto",
    )

def r2_put(r2, key: str, data: bytes, content_type: str = "application/octet-stream"):
    r2.put_object(Bucket=os.environ["R2_BUCKET"], Key=key,
                  Body=data, ContentType=content_type)

def r2_get(r2, key: str) -> bytes:
    return r2.get_object(Bucket=os.environ["R2_BUCKET"], Key=key)["Body"].read()

def r2_presigned(r2, key: str, expires: int = 86400) -> str:
    """Signed URL valid for `expires` seconds (default 24 h)."""
    return r2.generate_presigned_url(
        "get_object",
        Params    = {"Bucket": os.environ["R2_BUCKET"], "Key": key},
        ExpiresIn = expires,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 3.  Upstash Redis  (REST API — works in any runtime, no persistent TCP)
# ══════════════════════════════════════════════════════════════════════════════
def _redis_headers():
    return {"Authorization": f"Bearer {os.environ['UPSTASH_REDIS_REST_TOKEN']}"}

def redis_set(key: str, value: dict, ttl_s: int = 3600):
    import httpx
    base = os.environ["UPSTASH_REDIS_REST_URL"]
    encoded = json.dumps(value, separators=(",", ":"))
    httpx.post(f"{base}/set/{key}/{encoded}/ex/{ttl_s}",
               headers=_redis_headers(), timeout=5)

def redis_get(key: str) -> dict | None:
    import httpx
    base = os.environ["UPSTASH_REDIS_REST_URL"]
    r    = httpx.get(f"{base}/get/{key}", headers=_redis_headers(), timeout=5)
    val  = r.json().get("result")
    return json.loads(val) if val else None


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Dental segmentation
#     Primary  : SAM 2 guided by MediaPipe mouth landmarks
#     Fallback : MediaPipe polygon mask (if SAM2 fails or no GPU)
# ══════════════════════════════════════════════════════════════════════════════
_MOUTH_RING = [
    61,146,91,181,84,17,314,405,321,375,291,409,
    270,269,267,0,37,39,40,185,
    13,312,311,310,415,308,324,318,402,317,14,87,178,88,95,
    78,191,80,81,82,
]

def get_dental_mask(img_bgr) -> "np.ndarray":
    """Returns float32 soft mask [H,W] ∈ [0,1]."""
    import cv2, numpy as np, mediapipe as mp

    h, w = img_bgr.shape[:2]
    rgb   = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=True, max_num_faces=1,
        refine_landmarks=True, min_detection_confidence=0.5
    ) as fm:
        res = fm.process(rgb)

    if not res.multi_face_landmarks:
        raise ValueError("顔が検出できませんでした")

    lms  = res.multi_face_landmarks[0].landmark
    pts  = np.array([[int(lms[i].x * w), int(lms[i].y * h)]
                     for i in _MOUTH_RING], dtype=np.int32)
    cent = pts.mean(axis=0)

    # ── SAM2 path ──────────────────────────────────────────────────────────
    try:
        import torch
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model  = build_sam2(
            "sam2_hiera_s.yaml",
            "/opt/checkpoints/sam2.1_hiera_small.pt",
            device=device,
        )
        predictor = SAM2ImagePredictor(model)
        predictor.set_image(rgb)

        x0, y0 = pts.min(axis=0) - 28
        x1, y1 = pts.max(axis=0) + 28
        box    = np.array([max(0, x0), max(0, y0), min(w, x1), min(h, y1)])

        masks, _, _ = predictor.predict(
            point_coords     = cent[None],
            point_labels     = np.array([1]),
            box              = box[None],
            multimask_output = False,
        )
        mask = masks[0].astype(np.float32)
        del model, predictor
        torch.cuda.empty_cache()
        log.info("SAM2 segmentation OK")

    except Exception as e:
        log.warning(f"SAM2 skipped ({e}) — polygon fallback")
        mask = np.zeros((h, w), np.float32)
        cv2.fillPoly(mask, [pts], 1.0)

    # Feather edge for natural blending
    u8 = (mask * 255).astype(np.uint8)
    return cv2.GaussianBlur(u8, (0, 0), sigmaX=10).astype(np.float32) / 255.0


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Color harmonization  (Reinhard 2001 Lab transfer)
# ══════════════════════════════════════════════════════════════════════════════
def reinhard_match(src_bgr, tgt_bgr, mask) -> "np.ndarray":
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
        matched = (sl[:, :, ch] - sv.mean()) * (tv.std() + 1e-6) / (sv.std() + 1e-6) + tv.mean()
        sl[:, :, ch] = np.where(mask > 0.5, matched, sl[:, :, ch])
    return from_lab(sl)


# ══════════════════════════════════════════════════════════════════════════════
# 6.  Face alignment  (homography via MediaPipe outer-face landmarks)
# ══════════════════════════════════════════════════════════════════════════════
_FACE_IDX = [
    10,338,297,332,284,251,389,356,454,323,361,288,
    397,365,379,378,400,377,152,148,176,149,150,136,
    172,58,132,93,234,127,162,21,54,103,67,109,
]

def align_to_master(src, master) -> "np.ndarray":
    import cv2, numpy as np, mediapipe as mp

    h, w = master.shape[:2]

    def face_pts(img):
        with mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True, max_num_faces=1,
            min_detection_confidence=0.5
        ) as fm:
            res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks:
            return None
        lms = res.multi_face_landmarks[0].landmark
        ih, iw = img.shape[:2]
        return np.array([[lms[i].x * iw, lms[i].y * ih]
                         for i in _FACE_IDX], dtype=np.float32)

    sp, mp_ = face_pts(src), face_pts(master)
    if sp is None or mp_ is None:
        return cv2.resize(src, (w, h))

    H, _ = cv2.findHomography(sp, mp_, cv2.RANSAC, 5.0)
    if H is None:
        return cv2.resize(src, (w, h))
    return cv2.warpPerspective(src, H, (w, h))


# ══════════════════════════════════════════════════════════════════════════════
# 7.  Frame interpolation  (RAFT optical flow → warp-and-blend)
#     Using torchvision's built-in RAFT (no extra model download needed).
#     Forward-warp A and backward-warp B, blend at time t with visibility mask.
# ══════════════════════════════════════════════════════════════════════════════
_RAFT_MODEL = None

def _get_raft():
    global _RAFT_MODEL
    if _RAFT_MODEL is None:
        import torch
        from torchvision.models.optical_flow import raft_large, Raft_Large_Weights
        _RAFT_MODEL = raft_large(weights=Raft_Large_Weights.DEFAULT).cuda().eval()
        log.info("RAFT model loaded")
    return _RAFT_MODEL

def _flow_warp(img, flow):
    """Backward-warp img according to [2,H,W] flow field (cv2.remap)."""
    import cv2, numpy as np
    h, w   = img.shape[:2]
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x  = np.clip(gx + flow[0], 0, w - 1)
    map_y  = np.clip(gy + flow[1], 0, h - 1)
    return cv2.remap(img, map_x, map_y, cv2.INTER_LANCZOS4)

def _ease_cubic(t: float) -> float:
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2)**3 / 2

def interpolate_segment(a_bgr, b_bgr, n_frames: int) -> list:
    """Generate n_frames intermediate frames between a and b."""
    import torch, numpy as np
    from torchvision.transforms.functional import to_tensor

    raft   = _get_raft()
    device = "cuda"

    def to_raft(img):
        # RAFT expects [1,3,H,W] float32 in [0,255]
        t = to_tensor(img[..., ::-1].copy()).unsqueeze(0).to(device)
        return t * 255.0

    ta, tb = to_raft(a_bgr), to_raft(b_bgr)
    with torch.no_grad():
        flow_ab = raft(ta, tb)[-1][0].cpu().numpy()   # [2,H,W]
        flow_ba = raft(tb, ta)[-1][0].cpu().numpy()

    out = []
    for i in range(n_frames):
        raw_t = (i + 1) / (n_frames + 1)
        t     = _ease_cubic(raw_t)
        wa    = _flow_warp(a_bgr, flow_ab *  t)
        wb    = _flow_warp(b_bgr, flow_ba * (1 - t))
        blend = (wa.astype(np.float32) * (1 - t) +
                 wb.astype(np.float32) *  t).clip(0, 255).astype(np.uint8)
        out.append(blend)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 8.  GPU Function  —  full pipeline
# ══════════════════════════════════════════════════════════════════════════════
@app.function(
    image   = GPU_IMAGE,
    gpu     = "A10G",
    secrets = [SECRETS],
    timeout = 600,      # 10 min ceiling
    memory  = 32768,    # 32 GB RAM
)
def run_pipeline(job_id: str, frame_r2_keys: list[str],
                 duration_ms: int, fps: int):
    import cv2, numpy as np
    import ffmpeg as ff

    r2 = make_r2()

    def status(s: str, p: int = 0, url: str = ""):
        redis_set(f"job:{job_id}", {"status": s, "progress": p, "resultUrl": url})
        log.info(f"[{job_id}] {s} {p}%")

    try:
        # ── A: Download frames from R2 ────────────────────────────────────
        status("downloading", 2)
        raw_frames = []
        for key in frame_r2_keys:
            data = r2_get(r2, key)
            arr  = np.frombuffer(data, np.uint8)
            raw_frames.append(cv2.imdecode(arr, cv2.IMREAD_COLOR))

        master = raw_frames[-1].copy()   # After photo = immutable canvas
        H, W   = master.shape[:2]
        log.info(f"[{job_id}] {len(raw_frames)} frames, canvas {W}x{H}")

        # ── B: Composite each earlier frame onto master ────────────────────
        status("segmenting", 8)
        composited = []
        for i, src in enumerate(raw_frames):
            if i == len(raw_frames) - 1:
                composited.append(master)
                continue

            pct = 8 + int(i / len(raw_frames) * 28)
            status("segmenting", pct)

            try:
                warped     = align_to_master(src, master)
                mask       = get_dental_mask(warped)
                harmonized = reinhard_match(warped, master, mask)
                alpha      = mask[:, :, None]
                comp       = (harmonized.astype(np.float32) * alpha
                              + master.astype(np.float32) * (1 - alpha)
                              ).clip(0, 255).astype(np.uint8)
                composited.append(comp)
                log.info(f"[{job_id}] frame {i} composited OK")
            except Exception as e:
                log.warning(f"[{job_id}] frame {i} failed ({e}), using aligned src")
                composited.append(cv2.resize(src, (W, H)))

        # ── C: RAFT optical flow interpolation ────────────────────────────
        status("interpolating", 36)
        n_seg    = len(composited) - 1
        seg_ms   = duration_ms / max(1, n_seg)
        f_per_s  = max(1, round(seg_ms / 1000 * fps) - 1)   # frames between keyframes

        all_frames = [composited[0]]
        for si, (fa, fb) in enumerate(zip(composited[:-1], composited[1:])):
            pct = 36 + int(si / n_seg * 46)
            status("interpolating", pct)
            all_frames.extend(interpolate_segment(fa, fb, f_per_s))
            all_frames.append(fb)

        log.info(f"[{job_id}] total frames: {len(all_frames)}")

        # ── D: Encode MP4 ─────────────────────────────────────────────────
        status("encoding", 82)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            out_path = f.name

        proc = (
            ff.input("pipe:", format="rawvideo", pix_fmt="bgr24",
                     s=f"{W}x{H}", r=fps, framerate=fps)
            .output(out_path,
                    vcodec="libx264", pix_fmt="yuv420p",
                    crf=16, preset="fast",
                    movflags="+faststart",
                    **{"profile:v": "high", "level": "4.1"})
            .overwrite_output()
            .run_async(pipe_stdin=True, quiet=True)
        )
        for fr in all_frames:
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
        proc.wait()

        # ── E: Upload result to R2 ────────────────────────────────────────
        status("uploading", 95)
        result_key = f"results/{job_id}/morph.mp4"
        with open(out_path, "rb") as f:
            r2_put(r2, result_key, f.read(), "video/mp4")
        os.unlink(out_path)

        # Signed URL valid for 24 h
        signed_url = r2_presigned(r2, result_key, expires=86400)
        status("done", 100, signed_url)
        log.info(f"[{job_id}] pipeline complete → {signed_url}")

    except Exception as e:
        log.exception(f"[{job_id}] FATAL")
        redis_set(f"job:{job_id}", {
            "status": "error", "progress": 0,
            "resultUrl": "", "error": str(e)[:400],
        })


# ══════════════════════════════════════════════════════════════════════════════
# 9.  FastAPI web endpoints
#     URL: https://<modal-username>--caseflow-morph-web.modal.run
#
#     POST /api/morph/submit   — receives frames, spawns GPU job, returns jobId
#     GET  /api/morph/status   — polls Redis, returns {status, progress, resultUrl}
# ══════════════════════════════════════════════════════════════════════════════
from fastapi import FastAPI, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

web_app = FastAPI(title="CaseFlow Morph API")
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://caseflow-studio.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods  = ["POST", "GET", "OPTIONS"],
    allow_headers  = ["*"],
    allow_credentials = False,
)


@web_app.post("/api/morph/submit")
async def submit(
    frame      : list[UploadFile] = File(...,  description="Keyframe JPEGs in order"),
    durationMs : int              = Form(4000, description="Total animation duration ms"),
    fps        : int              = Form(30,   description="Output fps"),
):
    job_id = str(uuid.uuid4())

    # Upload every frame to R2 under this job's prefix
    r2          = make_r2()
    frame_keys  = []
    for i, f in enumerate(frame):
        data = await f.read()
        key  = f"uploads/{job_id}/frame_{i:03d}.jpg"
        r2_put(r2, key, data, "image/jpeg")
        frame_keys.append(key)
        log.info(f"[{job_id}] uploaded frame {i} → R2:{key}")

    # Store initial status so polling sees something immediately
    redis_set(f"job:{job_id}", {"status": "queued", "progress": 1, "resultUrl": ""})

    # Spawn GPU pipeline — returns immediately, runs in background
    run_pipeline.spawn(job_id, frame_keys, durationMs, fps)

    return JSONResponse({"jobId": job_id}, status_code=202)


@web_app.get("/api/morph/status")
async def job_status(jobId: str = Query(..., description="Job ID from /submit")):
    data = redis_get(f"job:{jobId}")
    if data is None:
        return JSONResponse(
            {"status": "unknown", "progress": 0, "resultUrl": "", "error": "Job not found"},
            status_code=404,
        )
    return JSONResponse(data)


@web_app.get("/health")
async def health():
    return {"ok": True}


@app.function(image=GPU_IMAGE, secrets=[SECRETS])
@modal.asgi_app()
def web():
    return web_app
