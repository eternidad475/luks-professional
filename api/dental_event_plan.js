// POST /api/dental_event_plan
// Auth: Authorization: Bearer <supabase access token>
// Body: { before: dataURL, after: dataURL, guide?: {...}, case_type_hint?: string }
//
// Gemini を「構造理解」にのみ使用する（最終フレーム生成には使わない）:
//   - 症例タイプ分類 (standard_dental_morph / appliance_cleanup / space_closure /
//     prosthetic_emergence / extraction_ortho / mixed_event / unknown)
//   - 局所イベント検出（ブラケット/ワイヤー/アタッチメント/欠損/抜歯スペース/補綴出現 等）
//   - マスク提案（正規化 0..1 の矩形）
//   - Before/After 対応づけ
// 返却は検証済みの構造化 JSON のみ。座標はすべて正規化 0..1。
//
// セキュリティ: API キーはサーバー側 env のみ（GEMINI_API_KEY →
// GOOGLE_GENERATIVE_AI_API_KEY → GOOGLE_API_KEY → AI_GATEWAY_API_KEY の順で解決）。
// キー値をログ・レスポンスに出さない。フロントには一切キーを渡さない。
// キー未設定時は「未設定」を正直に返し、フロントはローカルフォールバックで動作する。

const { createClient } = require('@supabase/supabase-js');

const GEMINI_MODEL = process.env.GEMINI_PLAN_MODEL || 'gemini-2.5-flash';

const CASE_TYPES = ['standard_dental_morph', 'appliance_cleanup', 'space_closure',
  'prosthetic_emergence', 'extraction_ortho', 'mixed_event', 'unknown'];
const EVENT_TYPES = ['bracket_removal', 'wire_removal', 'attachment_removal', 'missing_tooth',
  'prosthetic_emergence', 'extraction_space', 'space_closure', 'tooth_repositioning',
  'gingival_change', 'lip_frame_change', 'restoration_replacement'];
const REGIONS = ['upper_anterior', 'lower_anterior', 'left_posterior', 'right_posterior',
  'full_smile', 'unknown'];
const PHASES = ['pre_cleanup', 'main_morph', 'local_emergence', 'space_closure', 'final_blend'];
const MASK_KEYS = ['brackets', 'wires', 'attachments', 'missing_spaces',
  'prosthetic_emergence_regions', 'extraction_spaces', 'old_restorations'];

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

function normRect(r) {
  if (!r || typeof r !== 'object') return null;
  const x = clamp01(r.x), y = clamp01(r.y);
  const w = clamp01(r.w), h = clamp01(r.h);
  if (w <= 0.001 || h <= 0.001) return null;
  return { x: x, y: y, w: Math.min(w, 1 - x), h: Math.min(h, 1 - y) };
}

// Gemini の出力を厳密に検証・正規化する（スキーマ外は捨てる）。
function validatePlan(raw) {
  const out = {
    ok: true,
    photo_type: ['intraoral', 'smile', 'portrait'].indexOf(raw.photo_type) >= 0 ? raw.photo_type : 'unknown',
    retractor: raw.retractor === true ? true : raw.retractor === false ? false : 'unknown',
    case_type: CASE_TYPES.indexOf(raw.case_type) >= 0 ? raw.case_type : 'unknown',
    case_type_confidence: clamp01(raw.case_type_confidence),
    detected_events: [],
    masks: {},
    before_after_correspondence: [],
    missing_required: Array.isArray(raw.missing_required) ? raw.missing_required.slice(0, 12).map(String) : [],
    needs_manual_review: true // AI 提案は必ずユーザー確認を要求する
  };
  (Array.isArray(raw.detected_events) ? raw.detected_events : []).slice(0, 16).forEach(function (ev) {
    if (!ev || EVENT_TYPES.indexOf(ev.type) < 0) return;
    out.detected_events.push({
      type: ev.type,
      region: REGIONS.indexOf(ev.region) >= 0 ? ev.region : 'unknown',
      confidence: clamp01(ev.confidence),
      requires_local_processing: ev.requires_local_processing !== false,
      recommended_phase: PHASES.indexOf(ev.recommended_phase) >= 0 ? ev.recommended_phase : 'main_morph'
    });
  });
  MASK_KEYS.forEach(function (k) {
    const arr = raw.masks && Array.isArray(raw.masks[k]) ? raw.masks[k] : [];
    out.masks[k] = arr.slice(0, 12).map(normRect).filter(Boolean);
  });
  (Array.isArray(raw.before_after_correspondence) ? raw.before_after_correspondence : [])
    .slice(0, 32).forEach(function (c) {
      if (!c || typeof c !== 'object') return;
      const t = ['same_tooth', 'moved_tooth', 'appearing_structure', 'disappearing_structure', 'replacement'];
      if (t.indexOf(c.type) < 0) return;
      out.before_after_correspondence.push({
        before_id: String(c.before_id || '').slice(0, 8),
        after_id: String(c.after_id || '').slice(0, 8),
        type: c.type,
        confidence: clamp01(c.confidence)
      });
    });
  return out;
}

const PROMPT = [
  'You are a dental imaging analyst assisting a clinician-facing visualization tool.',
  'You are given a BEFORE image (first) and an AFTER image (second) of the same patient\'s dentition.',
  'Analyze the STRUCTURE of the transition only. Do NOT invent hidden anatomy. Do NOT make treatment decisions.',
  'Classify the case and detect local events. Respond with STRICT JSON only (no markdown, no commentary), using this schema:',
  '{"photo_type":"intraoral|smile|portrait|unknown","retractor":true|false,"case_type":"standard_dental_morph|appliance_cleanup|space_closure|prosthetic_emergence|extraction_ortho|mixed_event|unknown","case_type_confidence":0..1,',
  '"detected_events":[{"type":"bracket_removal|wire_removal|attachment_removal|missing_tooth|prosthetic_emergence|extraction_space|space_closure|tooth_repositioning|gingival_change|lip_frame_change|restoration_replacement","region":"upper_anterior|lower_anterior|left_posterior|right_posterior|full_smile|unknown","confidence":0..1,"requires_local_processing":true,"recommended_phase":"pre_cleanup|main_morph|local_emergence|space_closure|final_blend"}],',
  '"masks":{"brackets":[{"x":0..1,"y":0..1,"w":0..1,"h":0..1}],"wires":[],"attachments":[],"missing_spaces":[],"prosthetic_emergence_regions":[],"extraction_spaces":[],"old_restorations":[]},',
  '"before_after_correspondence":[{"before_id":"UR1","after_id":"UR1","type":"same_tooth|moved_tooth|appearing_structure|disappearing_structure|replacement","confidence":0..1}],',
  '"missing_required":[]}',
  'Mask coordinates are normalized 0..1 relative to the BEFORE image (x,y = top-left). Only include masks you can locate with reasonable confidence.',
  'Case type guidance: brackets/wires visible in BEFORE but absent in AFTER => appliance_cleanup (masks.brackets/wires on the BEFORE image).',
  'A tooth present in BEFORE but absent in AFTER with closed space => extraction_ortho. A gap/missing tooth in BEFORE restored in AFTER => prosthetic_emergence.',
  'Diastema/spacing closing => space_closure. General alignment/shade improvement => standard_dental_morph. Multiple simultaneous events => mixed_event.',
  'If you cannot classify confidently, use "unknown" with low confidence. Never fabricate teeth that are not visible.'
].join('\n');

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).json({ error: 'method_not_allowed' }); return; }
  try {
    const supaUrl = process.env.SUPABASE_URL;
    const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!supaUrl || !srKey) { res.status(500).json({ error: 'server_not_configured' }); return; }

    // 認証（既存の Stripe API と同じ: Supabase JWT 必須）
    const jwt = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!jwt) { res.status(401).json({ error: 'unauthorized' }); return; }
    const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });
    const { data: userData, error: userErr } = await admin.auth.getUser(jwt);
    if (userErr || !userData || !userData.user) { res.status(401).json({ error: 'unauthorized' }); return; }

    const body = req.body || {};
    const before = parseDataUrl(body.before);
    const after = parseDataUrl(body.after);
    if (!before || !after) { res.status(400).json({ error: 'before_and_after_required' }); return; }
    // ペイロード上限（画像はクライアントで縮小済みの想定）
    if (before.b64.length > 2600000 || after.b64.length > 2600000) {
      res.status(413).json({ error: 'image_too_large' }); return;
    }

    const key = resolveKey();
    if (!key) {
      // 正直なフォールバック: Gemini 未設定であることを明示して返す。
      res.status(200).json({
        ok: false, fallback: true, reason: 'gemini_not_configured',
        case_type: 'unknown', case_type_confidence: 0,
        detected_events: [], masks: {}, before_after_correspondence: [],
        needs_manual_review: true
      });
      return;
    }

    const hint = CASE_TYPES.indexOf(body.case_type_hint) >= 0
      ? ('\nThe clinician suggests the case type may be: ' + body.case_type_hint + '. Verify rather than assume.')
      : '';
    const gBody = {
      contents: [{
        parts: [
          { text: PROMPT + hint },
          { inline_data: { mime_type: before.mime, data: before.b64 } },
          { inline_data: { mime_type: after.mime, data: after.b64 } }
        ]
      }],
      generationConfig: { response_mime_type: 'application/json', temperature: 0.1, maxOutputTokens: 4096 }
    };

    const gUrl = 'https://generativelanguage.googleapis.com/v1beta/models/' + GEMINI_MODEL + ':generateContent';
    const gRes = await fetch(gUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
      body: JSON.stringify(gBody)
    });
    if (!gRes.ok) {
      const errTxt = (await gRes.text()).slice(0, 200);
      console.error('[dental_event_plan] gemini http', gRes.status, errTxt);
      res.status(200).json({ ok: false, fallback: true, reason: 'gemini_error', status: gRes.status, needs_manual_review: true });
      return;
    }
    const gJson = await gRes.json();
    const txt = (((gJson.candidates || [])[0] || {}).content || { parts: [] }).parts
      .map(function (p) { return p.text || ''; }).join('');
    let raw;
    try { raw = JSON.parse(txt); }
    catch (e) {
      // JSON 以外が返ったら失敗として扱う（勝手に補完しない）
      console.error('[dental_event_plan] non-JSON gemini output');
      res.status(200).json({ ok: false, fallback: true, reason: 'invalid_ai_json', needs_manual_review: true });
      return;
    }
    res.status(200).json(validatePlan(raw));
  } catch (e) {
    console.error('[dental_event_plan] error', e && e.message);
    res.status(500).json({ error: 'internal_error' });
  }
};
