"use client";

/**
 * CinematicCompare — CASEFLOW STUDIO™
 * ------------------------------------------------------------------
 * A symmetric, A24 / Oneohtrix-Point-Never-flavoured Before/After
 * comparison surface. Self-contained, zero external libraries.
 *
 *  • Dynamic gradient background (Color 1 / Color 2 hue + Blend Ratio)
 *  • Film-grain noise — pure SVG data-URI + CSS @keyframes,
 *    mix-blend-mode, pointer-events:none, 3–5% opacity.
 *  • Velocity-driven split-line halation that *inherits* the live
 *    gradient accent colour (CSS var), mix-blend-mode:screen.
 *  • Extreme typographic contrast: bold serif titles vs. cold
 *    monospace instrument readouts.
 *
 * Performance notes:
 *  - The split position and halation are written straight to CSS
 *    custom properties via refs (no React re-render per pointer move).
 *  - A single rAF loop drives the halation decay and self-stops when
 *    idle. Grain is a GPU-friendly transform animation.
 *
 * Drop into any React 18 / Next.js (app or pages) project.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";

export type CompareMeta = { label: string; value: string };

export type CinematicCompareProps = {
  beforeSrc: string;
  afterSrc: string;
  title?: string;
  subtitle?: string;
  /** instrument-style readouts rendered in the lower rail */
  meta?: CompareMeta[];
  /** dynamic gradient — HSL hue 0..360 */
  color1Hue?: number;
  color2Hue?: number;
  /** 0..1 — shifts the gradient focal point (the "blend ratio") */
  blendRatio?: number;
  /** halation / accent hue. Defaults to color2Hue so it inherits the gradient. */
  accentHue?: number;
  /** grain opacity, 0.03–0.05 looks best */
  grainOpacity?: number;
  /** initial split, 0..1 */
  initialSplit?: number;
  /** halation responsiveness (higher = brighter at lower speed) */
  halationGain?: number;
  className?: string;
  style?: CSSProperties;
};

/* Film-grain tile: feTurbulence baked into a data-URI (no network, no <img>). */
const GRAIN_URI =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>
       <filter id='n'>
         <feTurbulence type='fractalNoise' baseFrequency='0.82' numOctaves='2' stitchTiles='stitch'/>
         <feColorMatrix type='saturate' values='0'/>
       </filter>
       <rect width='100%' height='100%' filter='url(#n)'/>
     </svg>`.replace(/\s+/g, " ")
  );

export default function CinematicCompare({
  beforeSrc,
  afterSrc,
  title = "CASEFLOW STUDIO",
  subtitle = "Simulation / Reference",
  meta = [],
  color1Hue = 268,
  color2Hue = 322,
  blendRatio = 0.5,
  accentHue,
  grainOpacity = 0.045,
  initialSplit = 0.5,
  halationGain = 0.12,
  className,
  style,
}: CinematicCompareProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const clipRef = useRef<HTMLDivElement>(null);

  // pointer / physics state kept in refs so moving the slider never re-renders
  const split = useRef(initialSplit);
  const hal = useRef(0);
  const lastX = useRef(0);
  const lastT = useRef(0);
  const dragging = useRef(false);
  const raf = useRef<number | undefined>(undefined);

  const uid = useId().replace(/[:]/g, "");

  const setVar = useCallback((k: string, v: string | number) => {
    rootRef.current?.style.setProperty(k, String(v));
  }, []);

  // single self-stopping rAF loop: decays the halation toward 0
  const tick = useCallback(() => {
    hal.current *= 0.86;
    if (hal.current < 0.012) hal.current = 0;
    setVar("--halation", hal.current.toFixed(3));
    if (hal.current > 0 || dragging.current) {
      raf.current = requestAnimationFrame(tick);
    } else {
      raf.current = undefined;
    }
  }, [setVar]);

  const ensureLoop = useCallback(() => {
    if (raf.current == null) raf.current = requestAnimationFrame(tick);
  }, [tick]);

  const applyMove = useCallback(
    (clientX: number) => {
      const el = clipRef.current?.parentElement; // the stage
      if (!el) return;
      const r = el.getBoundingClientRect();
      const clamped = Math.min(r.width, Math.max(0, clientX - r.left));
      const s = clamped / r.width;
      split.current = s;
      setVar("--split", s.toFixed(4));

      // velocity → halation (px per ms), clamped, never lower than current bloom
      const now = performance.now();
      const dt = Math.max(1, now - lastT.current);
      const dx = clientX - lastX.current;
      const v = Math.abs(dx) / dt;
      const target = Math.min(1, v * halationGain);
      if (target > hal.current) hal.current = target;
      lastX.current = clientX;
      lastT.current = now;
      ensureLoop();
    },
    [ensureLoop, halationGain, setVar]
  );

  const onPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      dragging.current = true;
      lastX.current = e.clientX;
      lastT.current = performance.now();
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
      applyMove(e.clientX);
    },
    [applyMove]
  );

  // window-level move/up so a drag keeps tracking outside the stage
  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current) return;
      applyMove(e.clientX);
    };
    const up = () => {
      dragging.current = false;
      ensureLoop(); // let the bloom fade out
    };
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
      if (raf.current != null) cancelAnimationFrame(raf.current);
    };
  }, [applyMove, ensureLoop]);

  const rootStyle: CSSProperties = {
    // dynamic gradient + accent, all live-overridable from props/state
    ["--c1-h" as string]: color1Hue,
    ["--c2-h" as string]: color2Hue,
    ["--accent-h" as string]: accentHue ?? color2Hue,
    ["--blend" as string]: blendRatio,
    ["--grain-o" as string]: grainOpacity,
    ["--split" as string]: initialSplit,
    ["--halation" as string]: 0,
    ["--grain-uri" as string]: `url("${GRAIN_URI}")`,
    ...style,
  };

  return (
    <div
      ref={rootRef}
      className={`cc-root cc-${uid}${className ? ` ${className}` : ""}`}
      style={rootStyle}
    >
      <style dangerouslySetInnerHTML={{ __html: css(uid) }} />

      {/* dynamic gradient field */}
      <div className="cc-grad" aria-hidden />
      {/* film grain — writhing, blended into the gradient, never interactive */}
      <div className="cc-grain" aria-hidden />

      {/* perfectly centred 1080×1350 (4:5) comparison canvas */}
      <div className="cc-frame">
        <header className="cc-head">
          <h1 className="cc-title">{title}</h1>
          <span className="cc-sub">{subtitle}</span>
        </header>

        <div
          ref={stageRef}
          className="cc-stage"
          onPointerDown={onPointerDown}
          role="slider"
          aria-label="Before / After comparison"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(initialSplit * 100)}
          tabIndex={0}
        >
          {/* AFTER is the base; BEFORE is clipped over it so the wipe feels physical */}
          <img className="cc-img" src={afterSrc} alt="After / reference" draggable={false} />
          <div ref={clipRef} className="cc-clip">
            <img className="cc-img" src={beforeSrc} alt="Before" draggable={false} />
          </div>

          {/* corner instrument labels */}
          <span className="cc-tag cc-tag-l">BEFORE</span>
          <span className="cc-tag cc-tag-r">AFTER</span>

          {/* split line + halation bloom (colour inherited from --accent-h) */}
          <div className="cc-halation" aria-hidden />
          <div className="cc-divider" aria-hidden />
          <div className="cc-handle" aria-hidden>
            <span className="cc-handle-grip" />
          </div>
        </div>

        {/* cold monospace instrument rail */}
        {meta.length > 0 && (
          <dl className="cc-meta">
            {meta.map((m, i) => (
              <div className="cc-meta-cell" key={`${m.label}-${i}`}>
                <dt>{m.label}</dt>
                <dd>{m.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Scoped CSS. Keyframes are uid-scoped so multiple instances coexist. */
function css(uid: string): string {
  const k = `ccGrain_${uid}`;
  return `
.cc-${uid}.cc-root{
  position:relative; width:100%; min-height:100svh;
  display:grid; place-items:center; overflow:hidden;
  background:#070610; isolation:isolate;
  --serif: "Hiragino Mincho ProN","Yu Mincho",Didot,"Times New Roman",Georgia,serif;
  --mono: ui-monospace,"SF Mono","Roboto Mono","JetBrains Mono",Menlo,monospace;
}
/* dynamic gradient — Color 1 / Color 2 hue + Blend Ratio focal shift */
.cc-${uid} .cc-grad{
  position:absolute; inset:0; z-index:0; pointer-events:none;
  background:
    radial-gradient(140% 110% at calc(var(--blend)*100%) -10%,
      hsl(var(--c1-h) 78% 24%) 0%,
      hsl(var(--c2-h) 64% 15%) 52%,
      #06050c 100%),
    radial-gradient(90% 80% at calc(100% - var(--blend)*100%) 120%,
      hsl(var(--c2-h) 70% 16% / .9) 0%, transparent 60%);
  animation: ccDrift_${uid} 24s ease-in-out infinite alternate;
}
@keyframes ccDrift_${uid}{ from{filter:saturate(1) brightness(1)} to{filter:saturate(1.12) brightness(1.06)} }

/* film grain: scaled-up tile, jittered each frame for a writhing emulsion feel */
.cc-${uid} .cc-grain{
  position:absolute; inset:-60%; z-index:1; pointer-events:none;
  background-image:var(--grain-uri); background-size:160px 160px; background-repeat:repeat;
  opacity:var(--grain-o); mix-blend-mode:overlay;
  animation:${k} .5s steps(1) infinite; will-change:transform;
}
@keyframes ${k}{
  0%{transform:translate3d(0,0,0)} 10%{transform:translate3d(-4%,3%,0)}
  20%{transform:translate3d(3%,-5%,0)} 30%{transform:translate3d(-6%,2%,0)}
  40%{transform:translate3d(5%,5%,0)} 50%{transform:translate3d(-3%,-4%,0)}
  60%{transform:translate3d(6%,-2%,0)} 70%{transform:translate3d(-5%,4%,0)}
  80%{transform:translate3d(2%,-6%,0)} 90%{transform:translate3d(-4%,-3%,0)}
  100%{transform:translate3d(0,0,0)}
}
@media (prefers-reduced-motion:reduce){
  .cc-${uid} .cc-grain{animation:none}
  .cc-${uid} .cc-grad{animation:none}
}

/* symmetric layout + centred 1080×1350 canvas */
.cc-${uid} .cc-frame{
  position:relative; z-index:2;
  width:min(86vw, calc((100svh - 132px) * 0.8)); /* preserve 4:5 */
  max-width:540px; margin-inline:auto;
  display:flex; flex-direction:column; align-items:center; gap:18px;
  padding:24px 0;
}
.cc-${uid} .cc-head{ text-align:center; }
.cc-${uid} .cc-title{
  margin:0; font-family:var(--serif); font-weight:600;
  font-size:clamp(26px,4.4vw,40px); letter-spacing:.01em; line-height:1.02;
  color:#f4f1ff; text-shadow:0 1px 30px hsl(var(--accent-h) 80% 60% / .25);
}
.cc-${uid} .cc-sub{
  display:block; margin-top:8px; font-family:var(--mono);
  font-size:10px; letter-spacing:.32em; text-transform:uppercase;
  color:hsl(var(--c2-h) 30% 78% / .6);
}

.cc-${uid} .cc-stage{
  position:relative; width:100%; aspect-ratio:1080 / 1350; /* 4:5 */
  border-radius:8px; overflow:hidden; cursor:ew-resize; touch-action:none;
  background:#0b0a14; user-select:none;
  box-shadow:0 30px 90px -30px #000, 0 0 0 1px hsl(var(--c2-h) 40% 50% / .14);
}
.cc-${uid} .cc-img{
  position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
  display:block; -webkit-user-drag:none;
}
.cc-${uid} .cc-clip{
  position:absolute; inset:0; overflow:hidden;
  width:calc(var(--split) * 100%); will-change:width;
}
.cc-${uid} .cc-clip .cc-img{ width:calc(100% / var(--split)); max-width:none; }

.cc-${uid} .cc-tag{
  position:absolute; top:14px; z-index:4; font-family:var(--mono);
  font-size:9px; letter-spacing:.28em; padding:5px 9px; border-radius:999px;
  color:#e9e6f7; background:rgba(8,6,16,.42); backdrop-filter:blur(6px);
}
.cc-${uid} .cc-tag-l{ left:14px } .cc-${uid} .cc-tag-r{ right:14px }

/* halation: a vertical bloom centred on the split, screen-blended, accent-coloured */
.cc-${uid} .cc-halation{
  position:absolute; top:-8%; bottom:-8%; z-index:5; width:2px;
  left:calc(var(--split) * 100%); transform:translateX(-50%);
  mix-blend-mode:screen; pointer-events:none;
  background:hsl(var(--accent-h) 96% 72% / calc(var(--halation) * .85));
  box-shadow:
    0 0 calc(16px + var(--halation)*70px) calc(2px + var(--halation)*12px) hsl(var(--accent-h) 98% 64% / calc(var(--halation)*.6)),
    0 0 calc(48px + var(--halation)*150px) calc(8px + var(--halation)*40px) hsl(var(--c1-h) 92% 60% / calc(var(--halation)*.34));
  opacity:calc(.2 + var(--halation));
}
.cc-${uid} .cc-divider{
  position:absolute; top:0; bottom:0; z-index:6; width:1px;
  left:calc(var(--split) * 100%); transform:translateX(-50%);
  background:linear-gradient(180deg, transparent, rgba(255,255,255,.9) 12%, rgba(255,255,255,.9) 88%, transparent);
  pointer-events:none;
}
.cc-${uid} .cc-handle{
  position:absolute; top:50%; z-index:7; left:calc(var(--split) * 100%);
  width:38px; height:38px; transform:translate(-50%,-50%);
  border-radius:50%; pointer-events:none;
  display:grid; place-items:center;
  background:rgba(10,8,18,.32); backdrop-filter:blur(4px);
  box-shadow:0 0 0 1px rgba(255,255,255,.55), 0 0 calc(10px + var(--halation)*40px) hsl(var(--accent-h) 96% 66% / calc(.25 + var(--halation)*.6));
}
.cc-${uid} .cc-handle-grip{
  width:14px; height:14px; border-radius:50%;
  background:radial-gradient(circle at 50% 40%, #fff, hsl(var(--accent-h) 60% 86%));
}

/* cold monospace instrument rail — extreme contrast against the serif title */
.cc-${uid} .cc-meta{
  margin:2px 0 0; width:100%;
  display:grid; grid-template-columns:repeat(auto-fit,minmax(64px,1fr)); gap:1px;
  background:hsl(var(--c2-h) 30% 50% / .12);
  border:1px solid hsl(var(--c2-h) 30% 50% / .14); border-radius:6px; overflow:hidden;
}
.cc-${uid} .cc-meta-cell{ padding:9px 10px; background:rgba(7,6,14,.5); text-align:center; }
.cc-${uid} .cc-meta dt{
  font-family:var(--mono); font-size:8px; letter-spacing:.22em; text-transform:uppercase;
  color:hsl(var(--c2-h) 24% 74% / .55); margin:0 0 3px;
}
.cc-${uid} .cc-meta dd{
  margin:0; font-family:var(--serif); font-weight:600; font-size:17px;
  color:#f1eeff; letter-spacing:.01em; line-height:1;
}
`.trim();
}
