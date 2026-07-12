// POST /api/feedback/submit
// CaseFlow Feedback Engine™ — structured clinical review submission.
// Auth: Authorization: Bearer <supabase access token>. user_id is taken from the
// verified token, NEVER from the request body. Feedback does not touch tokens/billing.
//
// Writes one row to public.caseflow_feedback_reviews (RLS-owned by the user).
// No raw patient images or landmark arrays are accepted or stored.

const { createClient } = require('@supabase/supabase-js');

const ARTIFACT_TYPES = ['image', 'video', 'preview'];
const STUDIO_MODULES = ['visual_simulation', 'morphing_video', 'photo_manager'];
const RATINGS = ['good', 'bad'];

// Stable reason-tag allowlist (§7 good + §8 bad). Unknown tags are rejected.
const REASON_TAGS = new Set([
  // good
  'natural', 'believable_beauty', 'clinically_convincing', 'good_smile_design',
  'teeth_type_worked', 'face_preserved', 'patient_friendly', 'smooth_morphing',
  'matches_intention',
  // bad
  'too_artificial', 'not_clinically_plausible', 'tooth_shape_off', 'wrong_teeth_type',
  'shade_off', 'alignment_off', 'incisal_line_off', 'smile_frame_off', 'gingiva_wrong',
  'face_identity_changed', 'lip_expression_changed', 'morph_not_smooth', 'warp_unusual',
  'flicker_ghosting', 'too_much_correction', 'too_little_correction', 'other'
]);

const MAX_COMMENT = 2000;
const MAX_META_BYTES = 16 * 1024; // per jsonb field, defensive cap

function jsonField(v) {
  if (v == null) return null;
  try {
    const s = JSON.stringify(v);
    if (s.length > MAX_META_BYTES) return null; // silently drop oversized metadata, do not fail
    return v;
  } catch (e) { return null; }
}

function textOrNull(v, max) {
  if (v == null) return null;
  const s = String(v);
  return s.length ? s.slice(0, max) : null;
}

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
    const userId = userData.user.id;

    let body = req.body;
    if (typeof body === 'string') { try { body = JSON.parse(body); } catch (e) { res.status(400).json({ error: 'invalid_json' }); return; } }
    if (!body || typeof body !== 'object') { res.status(400).json({ error: 'invalid_body' }); return; }

    // ---- validation (user-safe errors, never leak DB internals) ----
    const outputId = textOrNull(body.output_id, 200);
    if (!outputId) { res.status(400).json({ error: 'output_id_required' }); return; }

    const rating = String(body.rating || '');
    if (RATINGS.indexOf(rating) < 0) { res.status(400).json({ error: 'invalid_rating' }); return; }

    const artifactType = String(body.artifact_type || '');
    if (ARTIFACT_TYPES.indexOf(artifactType) < 0) { res.status(400).json({ error: 'invalid_artifact_type' }); return; }

    const studioModule = String(body.studio_module || '');
    if (STUDIO_MODULES.indexOf(studioModule) < 0) { res.status(400).json({ error: 'invalid_studio_module' }); return; }

    let reasonTags = Array.isArray(body.reason_tags) ? body.reason_tags : [];
    reasonTags = Array.from(new Set(reasonTags.map(String)));
    for (let i = 0; i < reasonTags.length; i++) {
      if (!REASON_TAGS.has(reasonTags[i])) { res.status(400).json({ error: 'invalid_reason_tag' }); return; }
    }
    if (reasonTags.length > 12) reasonTags = reasonTags.slice(0, 12);

    const comment = textOrNull(body.comment, MAX_COMMENT);

    const row = {
      user_id: userId, // from the verified token only
      workspace_id: textOrNull(body.workspace_id, 64),
      project_id: textOrNull(body.project_id, 64),
      case_id: textOrNull(body.case_id, 64),
      patient_id: textOrNull(body.patient_id, 64),
      output_id: outputId,
      original_output_id: textOrNull(body.original_output_id, 200),
      refined_output_id: textOrNull(body.refined_output_id, 200),
      artifact_type: artifactType,
      studio_module: studioModule,
      rating: rating,
      reason_tags: reasonTags,
      comment: comment,
      selected_teeth_type: jsonField(body.selected_teeth_type),
      patient_context: jsonField(body.patient_context),
      prompt_snapshot: textOrNull(body.prompt_snapshot, 8000),
      slider_snapshot: jsonField(body.slider_snapshot),
      generation_metadata: jsonField(body.generation_metadata),
      model_metadata: jsonField(body.model_metadata),
      morph_metadata: jsonField(body.morph_metadata),
      token_metadata: jsonField(body.token_metadata),
      use_for_personalization: body.use_for_personalization === false ? false : true,
      use_for_aggregate_learning: body.use_for_aggregate_learning === true // default false
    };

    const ins = await admin.from('caseflow_feedback_reviews')
      .insert(row).select('id, created_at').single();
    if (ins.error) {
      console.error('[feedback submit] insert failed', ins.error && ins.error.message);
      const msg = String(ins.error.message || '');
      if (/does not exist|schema cache/i.test(msg)) { res.status(503).json({ error: 'feedback_not_enabled' }); return; }
      res.status(500).json({ error: 'submit_failed' });
      return;
    }

    res.status(200).json({ ok: true, feedback_id: ins.data.id, created_at: ins.data.created_at });
  } catch (e) {
    console.error('[feedback submit] error', e && e.message);
    res.status(500).json({ error: 'internal_error' });
  }
};
