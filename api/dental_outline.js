// POST /api/dental_outline
// Auth: Authorization: Bearer <supabase access token>
// Body: { before: dataURL, after: dataURL }
//
// RE:Flex 型モーフの自動化のための「歯牙輪郭抽出」専用エンドポイント。
// Gemini を「構造理解」(歯1本ごとの閉輪郭ポリゴン + FDI歯番) にのみ使用する。
// 最終フレームの生成には一切使わない（描画は常にローカルの mesh warp）。
// 返却は検証済みの構造化 JSON のみ。座標はすべて正規化 0..1（各画像基準）。
//
// セキュリティ: API キーはサーバー側 env のみ（GEMINI_API_KEY →
// GOOGLE_GENERATIVE_AI_API_KEY → GOOGLE_API_KEY → AI_GATEWAY_API_KEY の順で解決）。
// キー値をログ・レスポンスに出さない。キー未設定時は「未設定」を正直に返し、
// フロントはローカル検出（画像処理）へフォールバックする。

const { createClient } = require('@supabase/supabase-js');

const GEMINI_MODEL = process.env.GEMINI_OUTLINE_MODEL || 'gemini-2.5-flash';

function resolveKey() {
  return process.env.GEMINI_API_KEY
    || process.env.GOOGLE_GENERATIVE_AI_API_KEY
    || process.env.GOOGLE_API_KEY
    || process.env.AI_GATEWAY_API_KEY
    || null;
}

function parseDataUrl(d) {
  const m = /^data:([^;]+);base64,(.+)$/.exec(String(d || ''));
  if (!m) return null;
  return { mime: m[1], b64: m[2] };
}

function clamp01(v) { const n = Number(v); return isNaN(n) ? 0 : Math.max(0, Math.min(1, n)); }

// FDI 2桁（11-48 乳歯51-85も許容）。それ以外の表記は "unknown" に落とす。
function normFdi(v) {
  const s = String(v == null ? '' : v).trim();
  return /^[1-8][1-8]$/.test(s) ? s : 'unknown';
}

// 1歯分の輪郭: 6〜48点の閉ポリゴン。点数不足・退化ポリゴンは捨てる。
function normTooth(t) {
  if (!t || !Array.isArray(t.poly)) return null;
  const poly = t.poly.slice(0, 48).map(function (p) {
    if (Array.isArray(p) && p.length >= 2) return [clamp01(p[0]), clamp01(p[1])];
    if (p && typeof p === 'object') return [clamp01(p.x), clamp01(p.y)];
    return null;
  }).filter(Boolean);
  if (poly.length < 6) return null;
  let minX = 1, maxX = 0, minY = 1, maxY = 0;
  poly.forEach(function (p) {
    if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
    if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
  });
  if ((maxX - minX) < 0.008 || (maxY - minY) < 0.008) return null; // 退化
  return { fdi: normFdi(t.fdi), poly: poly, confidence: clamp01(t.confidence) };
}

function normSide(side) {
  const teeth = (side && Array.isArray(side.teeth) ? side.teeth : [])
    .slice(0, 24).map(normTooth).filter(Boolean);
  return { teeth: teeth };
}

const PROMPT = [
  'You are a dental imaging analyst tracing precise per-tooth masks for a morphing tool (like manually rotoscoping each tooth in After Effects).',
  'You receive a BEFORE intraoral/smile photo (first image) and an AFTER photo (second image) of the same patient.',
  'For EACH image, trace the visible crown outline of EACH clearly visible tooth as a CLOSED polygon that hugs the true crown silhouette tightly.',
  'Precision requirements (these are essential — trace them carefully, do not approximate with a rounded blob):',
  '1. INCISAL / OCCLUSAL EDGE: for upper and lower anterior teeth, place SEVERAL points along the incisal edge so its exact contour (including chips, wear, curvature) is captured, not a single flat line.',
  '2. INTERPROXIMAL CONTACTS: follow the mesial and distal surfaces down into each interproximal contact point. Where there is a gap/space (diastema) or a missing/worn area, trace the real edge of the space — do NOT bridge across it.',
  '3. GINGIVAL SCALLOP: follow the scalloped gingival margin (the zenith and the interdental papilla curve) precisely along the top of each crown — this scallop shape is required.',
  'Rules:',
  '- One polygon per tooth. 14 to 30 points, ordered clockwise, denser where curvature is high (incisal edge, line angles, papilla).',
  '- Coordinates normalized 0..1 relative to THAT image: [x, y], x rightward, y downward. Use full decimal precision.',
  '- Label each tooth with its FDI two-digit number (11-48). Use the SAME FDI number for the same tooth in both images so they can be matched. Double-check central incisors are 11/21 and laterals 12/22.',
  '- Only outline teeth whose crown silhouette is clearly visible; skip badly blurred or mostly hidden teeth. Never invent teeth or edges you cannot see.',
  '- A tooth missing in one image simply has no entry for that image (do not fabricate it).',
  'Respond with STRICT JSON only (no markdown), schema:',
  '{"before":{"teeth":[{"fdi":"11","confidence":0..1,"poly":[[0.42,0.31],[0.44,0.30], "..."]}]},"after":{"teeth":[ "..." ]}}'
].join('\n');

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).json({ error: 'method_not_allowed' }); return; }
  try {
    const supaUrl = process.env.SUPABASE_URL;
    const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!supaUrl || !srKey) { res.status(500).json({ error: 'server_not_configured' }); return; }

    const jwt = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!jwt) { res.status(401).json({ error: 'unauthorized' }); return; }
    const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });
    const { data: userData, error: userErr } = await admin.auth.getUser(jwt);
    if (userErr || !userData || !userData.user) { res.status(401).json({ error: 'unauthorized' }); return; }

    const body = req.body || {};
    const before = parseDataUrl(body.before);
    const after = parseDataUrl(body.after);
    if (!before || !after) { res.status(400).json({ error: 'before_and_after_required' }); return; }
    if (before.b64.length > 2600000 || after.b64.length > 2600000) {
      res.status(413).json({ error: 'image_too_large' }); return;
    }

    const key = resolveKey();
    if (!key) {
      res.status(200).json({ ok: false, fallback: true, reason: 'gemini_not_configured' });
      return;
    }

    const gBody = {
      contents: [{
        parts: [
          { text: PROMPT },
          { inline_data: { mime_type: before.mime, data: before.b64 } },
          { inline_data: { mime_type: after.mime, data: after.b64 } }
        ]
      }],
      generationConfig: { response_mime_type: 'application/json', temperature: 0, maxOutputTokens: 32768 }
    };

    const gUrl = 'https://generativelanguage.googleapis.com/v1beta/models/' + GEMINI_MODEL + ':generateContent';
    const gRes = await fetch(gUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
      body: JSON.stringify(gBody)
    });
    if (!gRes.ok) {
      const errTxt = (await gRes.text()).slice(0, 200);
      console.error('[dental_outline] gemini http', gRes.status, errTxt);
      res.status(200).json({ ok: false, fallback: true, reason: 'gemini_error', status: gRes.status });
      return;
    }
    const gJson = await gRes.json();
    const txt = (((gJson.candidates || [])[0] || {}).content || { parts: [] }).parts
      .map(function (p) { return p.text || ''; }).join('');
    let raw;
    try { raw = JSON.parse(txt); }
    catch (e) {
      console.error('[dental_outline] non-JSON gemini output');
      res.status(200).json({ ok: false, fallback: true, reason: 'invalid_ai_json' });
      return;
    }
    const beforeSide = normSide(raw.before);
    const afterSide = normSide(raw.after);
    if (beforeSide.teeth.length < 2 || afterSide.teeth.length < 2) {
      res.status(200).json({ ok: false, fallback: true, reason: 'insufficient_teeth',
        before: beforeSide, after: afterSide });
      return;
    }
    res.status(200).json({ ok: true, before: beforeSide, after: afterSide });
  } catch (e) {
    console.error('[dental_outline] error', e && e.message);
    res.status(500).json({ error: 'internal_error' });
  }
};
