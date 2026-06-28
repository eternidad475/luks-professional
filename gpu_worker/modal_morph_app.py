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
    """Download SAM2-Small and RAFT weights into the image (build-time only)."""
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

    # RAFT-Large  (torchvision built-in — caches to ~/.cache/torch/hub)
    print("Caching RAFT weights …")
    from torchvision.models.optical_flow import raft_large, Raft_Large_Weights
    raft_large(weights=Raft_Large_Weights.DEFAULT)
    print("  → RAFT ready")


GPU_IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg", "libgl1-mesa-glx", "libglib2.0-0",
        "libsm6", "libxext6", "libxrender-dev", "git",
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
def _redis_hdr():
    return {"Authorization": f"Bearer {os.environ['UPSTASH_REDIS_REST_TOKEN']}"}

def redis_set(key: str, val: dict, ttl: int = 7200):
    import httpx
    base    = os.environ["UPSTASH_REDIS_REST_URL"]
    encoded = json.dumps(val, separators=(",", ":"))
    r = httpx.post(f"{base}/pipeline",
                   json=[["SET", key, encoded, "EX", ttl]],
                   headers=_redis_hdr(), timeout=5)
    log.debug(f"redis_set {key}: {r.status_code}")

def redis_get(key: str) -> dict | None:
    import httpx
    base = os.environ["UPSTASH_REDIS_REST_URL"]
    r    = httpx.post(f"{base}/pipeline",
                      json=[["GET", key]],
                      headers=_redis_hdr(), timeout=5)
    results = r.json()
    raw = results[0].get("result") if results else None
    return json.loads(raw) if raw else None


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

def interp_segment(a_bgr, b_bgr, n: int) -> list:
    import torch, numpy as np
    from torchvision.transforms.functional import to_tensor

    raft = _get_raft()

    def prep(img):
        t = to_tensor(img[..., ::-1].copy()).unsqueeze(0).cuda()
        return t * 255.0

    ta, tb = prep(a_bgr), prep(b_bgr)
    with torch.no_grad():
        flow_ab = raft(ta, tb)[-1][0].cpu().numpy()
        flow_ba = raft(tb, ta)[-1][0].cpu().numpy()

    frames = []
    for i in range(n):
        t  = _ease((i + 1) / (n + 1))
        wa = _warp(a_bgr, flow_ab *  t)
        wb = _warp(b_bgr, flow_ba * (1 - t))
        blend = (wa.astype(np.float32) * (1 - t) +
                 wb.astype(np.float32) *  t).clip(0, 255).astype(np.uint8)
        frames.append(blend)
    return frames


# ══════════════════════════════════════════════════════════════════════════════
# 9.  GPU Function  —  the full "Static Canvas" pipeline
# ══════════════════════════════════════════════════════════════════════════════
@app.function(
    image   = GPU_IMAGE,
    gpu     = "A10G",
    secrets = [SECRETS],
    timeout = 600,      # 10 min ceiling per job
    memory  = 32768,
)
def run_pipeline(job_id: str, frame_keys: list[str],
                 duration_ms: int, fps: int):
    import cv2, numpy as np
    import ffmpeg as ff

    r2 = _r2()

    def status(s: str, p: int = 0, url: str = ""):
        redis_set(f"job:{job_id}", {"status": s, "progress": p, "resultUrl": url})
        log.info(f"[{job_id}] {s} {p}%")

    try:
        # A ── Download frames from R2 ─────────────────────────────────────
        status("downloading", 2)
        raw = []
        for key in frame_keys:
            arr = np.frombuffer(r2_get(r2, key), np.uint8)
            raw.append(cv2.imdecode(arr, cv2.IMREAD_COLOR))

        master = raw[-1].copy()   # After photo = immutable canvas
        H, W   = master.shape[:2]
        log.info(f"[{job_id}] {len(raw)} frames · canvas {W}×{H}")

        # B ── Composite each earlier frame onto master ────────────────────
        status("segmenting", 8)
        composited = []
        for i, src in enumerate(raw):
            if i == len(raw) - 1:
                composited.append(master)
                continue
            pct = 8 + int(i / len(raw) * 28)
            status("segmenting", pct)
            try:
                warped = align_to_master(src, master)
                msk    = dental_mask(warped)
                harm   = color_match(warped, master, msk)
                a      = msk[:, :, None]
                comp   = (harm.astype(np.float32) * a +
                          master.astype(np.float32) * (1 - a)
                          ).clip(0, 255).astype(np.uint8)
                composited.append(comp)
            except Exception as e:
                log.warning(f"[{job_id}] frame {i} fallback: {e}")
                composited.append(cv2.resize(src, (W, H)))

        # C ── RAFT interpolation ──────────────────────────────────────────
        status("interpolating", 36)
        n_seg   = len(composited) - 1
        seg_ms  = duration_ms / max(1, n_seg)
        f_per_s = max(1, round(seg_ms / 1000 * fps) - 1)

        all_frames = [composited[0]]
        for si, (fa, fb) in enumerate(zip(composited[:-1], composited[1:])):
            status("interpolating", 36 + int(si / n_seg * 46))
            all_frames.extend(interp_segment(fa, fb, f_per_s))
            all_frames.append(fb)
        log.info(f"[{job_id}] {len(all_frames)} total frames")

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
    frame      : list[UploadFile] = File(...),
    durationMs : int              = Form(4000),
    fps        : int              = Form(30),
):
    job_id = str(uuid.uuid4())
    r2     = _r2()

    frame_keys = []
    for i, f in enumerate(frame):
        data = await f.read()
        key  = f"uploads/{job_id}/frame_{i:03d}.jpg"
        r2_put(r2, key, data, "image/jpeg")
        frame_keys.append(key)
        log.info(f"[{job_id}] uploaded frame {i}")

    redis_set(f"job:{job_id}", {"status": "queued", "progress": 1, "resultUrl": ""})

    # Non-blocking spawn — returns immediately, GPU runs in background
    run_pipeline.spawn(job_id, frame_keys, durationMs, fps)

    return JSONResponse({"jobId": job_id})


@web_app.get("/api/morph/status")
async def job_status(jobId: str = Query(...)):
    data = redis_get(f"job:{jobId}")
    if data is None:
        return JSONResponse({"status": "unknown", "progress": 0,
                             "resultUrl": "", "error": "job not found"},
                            status_code=404)
    return JSONResponse(data)


@web_app.get("/health")
async def health():
    return {"ok": True, "service": "caseflow-morph"}


# ── Wire FastAPI into Modal ───────────────────────────────────────────────────
@app.function(
    image      = GPU_IMAGE,
    secrets    = [SECRETS],
    min_containers = 1,      # 1 warm instance — eliminates cold start for web requests
)
@modal.asgi_app()
def web():
    return web_app
