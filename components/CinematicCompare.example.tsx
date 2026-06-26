"use client";

/**
 * Example usage of <CinematicCompare />.
 *
 * Next.js (app router): drop this in e.g. app/compare/page.tsx,
 * or import <CinematicCompare /> directly anywhere on the client.
 *
 * The gradient (Color 1 / Color 2 hue + Blend Ratio) and the accent
 * hue can be driven from your existing palette state — the halation
 * inherits whatever `accentHue` (defaults to color2Hue) you pass, so
 * it always glows in the environment colour.
 */

import { useState } from "react";
import CinematicCompare from "./CinematicCompare";

export default function CompareDemo() {
  // Wire these to your existing palette controls / store.
  const [c1, setC1] = useState(268); // Color 1 hue
  const [c2, setC2] = useState(322); // Color 2 hue
  const [blend, setBlend] = useState(0.5); // Blend Ratio

  return (
    <CinematicCompare
      beforeSrc="/cases/cf-002-before.jpg"
      afterSrc="/cases/cf-002-after.jpg"
      title="CASEFLOW STUDIO"
      subtitle="Simulation / Reference"
      color1Hue={c1}
      color2Hue={c2}
      blendRatio={blend}
      // accentHue defaults to color2Hue → halation inherits the gradient accent
      grainOpacity={0.045}
      meta={[
        { label: "Case", value: "CF-002" },
        { label: "Shade", value: "A2" },
        { label: "Align", value: "92%" },
        { label: "Concept", value: "Hybrid" },
      ]}
    />
  );
}
