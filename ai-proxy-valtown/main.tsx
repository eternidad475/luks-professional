/*
 * Caseflow Studio – AI simulation proxy (Val Town HTTP val)
 *
 * Paste this whole file into a new HTTP val at https://www.val.town
 * Then add an Environment Variable named GEMINI_API_KEY (your Google AI Studio key).
 *
 * The val exposes:
 *   GET  /            -> { ok:true, ... }              (status check)
 *   POST /  or /simulate  { image: dataURL, prompt }   -> { image: dataURL }
 *
 * Patient identity is additionally guaranteed in the app, which pastes only the
 * mouth region of the AI result back onto the original photo. CORS is wide open
 * so the browser app can call it from any origin.
 */

const GEMINI_MODEL = "gemini-2.5-flash-image";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function parseDataUrl(d: string) {
  const m = /^data:([^;]+);base64,(.*)$/.exec(d || "");
  if (m) return { mime: m[1], b64: m[2] };
  return { mime: "image/jpeg", b64: (d || "").replace(/^data:.*?,/, "") };
}

async function viaGemini(imageDataUrl: string, prompt: string) {
  const key = Deno.env.get("GEMINI_API_KEY");
  if (!key) throw new Error("GEMINI_API_KEY not set");
  const { mime, b64 } = parseDataUrl(imageDataUrl);
  const url =
    `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
  const body = {
    contents: [{
      parts: [
        { text: prompt },
        { inline_data: { mime_type: mime, data: b64 } },
      ],
    }],
    generationConfig: { responseModalities: ["IMAGE"] },
  };
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": key },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error("Gemini " + r.status + " " + (await r.text()).slice(0, 300));
  const j = await r.json();
  const parts = j?.candidates?.[0]?.content?.parts || [];
  const part = parts.find((p: any) => p.inlineData || p.inline_data);
  const inl = part && (part.inlineData || part.inline_data);
  if (!inl || !inl.data) throw new Error("Gemini returned no image");
  return `data:${inl.mimeType || inl.mime_type || "image/png"};base64,${inl.data}`;
}

export default async function (req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

  if (req.method === "GET") {
    return Response.json({ ok: true, provider: "gemini", model: GEMINI_MODEL }, { headers: CORS });
  }

  try {
    const { image, prompt } = await req.json();
    if (!image) {
      return Response.json({ error: "image (dataURL) required" }, { status: 400, headers: CORS });
    }
    const p = prompt ||
      "Photorealistic dental after-treatment simulation; keep the same patient, face and composition; modify only the teeth and gingiva; natural enamel texture; no text, no watermark.";
    const out = await viaGemini(image, p);
    return Response.json({ image: out }, { headers: CORS });
  } catch (e) {
    return Response.json({ error: String((e as Error)?.message || e) }, { status: 500, headers: CORS });
  }
}
