/*
 * Caseflow Studio – AI simulation proxy (Replit / Node, Autoscale-friendly)
 *
 * Holds your image-API key server-side and forwards a single request:
 *   POST /simulate  { image: dataURL, prompt, params, concept, targets }
 *   -> { image: dataURL }   (the generated after-image)
 *
 * Default provider is Google Gemini (Flash Image / "Nano Banana"): cheapest and
 * best at identity-preserving instructed edits. Set PROVIDER=openai to use
 * OpenAI gpt-image-1 instead. Patient-identity is additionally guaranteed on the
 * client (the app pastes only the mouth region back onto the original photo), so
 * this proxy stays dependency-light and does no image manipulation itself.
 *
 * Secrets (Replit "Secrets" / .env):
 *   PROVIDER       gemini | openai           (default: gemini)
 *   GEMINI_API_KEY <Google AI Studio key>    (required for gemini)
 *   GEMINI_MODEL   gemini-2.5-flash-image     (override if the id changes)
 *   OPENAI_API_KEY <OpenAI key>              (required for openai)
 *   OPENAI_MODEL   gpt-image-1
 *   ALLOW_ORIGIN   *                          (or your site origin)
 */
const express = require('express');
const app = express();
app.use(express.json({ limit: '25mb' }));

// CORS (the browser app calls this from another origin)
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', process.env.ALLOW_ORIGIN || '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

const PROVIDER     = (process.env.PROVIDER || 'gemini').toLowerCase();
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-2.5-flash-image';
const OPENAI_MODEL = process.env.OPENAI_MODEL || 'gpt-image-1';

function parseDataUrl(d) {
  const m = /^data:([^;]+);base64,(.*)$/.exec(d || '');
  if (m) return { mime: m[1], b64: m[2] };
  return { mime: 'image/jpeg', b64: (d || '').replace(/^data:.*?,/, '') };
}

async function viaGemini(imageDataUrl, prompt) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error('GEMINI_API_KEY not set');
  const { mime, b64 } = parseDataUrl(imageDataUrl);
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;
  const body = {
    contents: [{ parts: [ { text: prompt }, { inline_data: { mime_type: mime, data: b64 } } ] }],
    generationConfig: { responseModalities: ['IMAGE'] }
  };
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error('Gemini ' + r.status + ' ' + (await r.text()).slice(0, 300));
  const j = await r.json();
  const parts = ((((j.candidates || [])[0] || {}).content) || {}).parts || [];
  const part = parts.find(p => p.inlineData || p.inline_data);
  const inl = part && (part.inlineData || part.inline_data);
  if (!inl || !inl.data) throw new Error('Gemini returned no image');
  return `data:${inl.mimeType || inl.mime_type || 'image/png'};base64,${inl.data}`;
}

async function viaOpenAI(imageDataUrl, prompt) {
  const key = process.env.OPENAI_API_KEY;
  if (!key) throw new Error('OPENAI_API_KEY not set');
  const { mime, b64 } = parseDataUrl(imageDataUrl);
  const buf = Buffer.from(b64, 'base64');
  const form = new FormData();
  form.append('model', OPENAI_MODEL);
  form.append('prompt', prompt);
  form.append('image', new Blob([buf], { type: mime }), 'image.' + (mime.includes('png') ? 'png' : 'jpg'));
  const r = await fetch('https://api.openai.com/v1/images/edits', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + key },
    body: form
  });
  if (!r.ok) throw new Error('OpenAI ' + r.status + ' ' + (await r.text()).slice(0, 300));
  const j = await r.json();
  const b = (((j.data || [])[0]) || {}).b64_json;
  if (!b) throw new Error('OpenAI returned no image');
  return `data:image/png;base64,${b}`;
}

app.get('/', (req, res) => res.json({ ok: true, provider: PROVIDER, model: PROVIDER === 'openai' ? OPENAI_MODEL : GEMINI_MODEL }));

app.post('/simulate', async (req, res) => {
  try {
    const { image, prompt } = req.body || {};
    if (!image) return res.status(400).json({ error: 'image (dataURL) required' });
    const p = prompt ||
      'Photorealistic dental after-treatment simulation; keep the same patient, face and composition; modify only the teeth and gingiva; natural enamel texture; no text, no watermark.';
    const out = (PROVIDER === 'openai') ? await viaOpenAI(image, p) : await viaGemini(image, p);
    res.json({ image: out });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: String((e && e.message) || e) });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Caseflow AI proxy listening on ${PORT} (provider=${PROVIDER})`));
