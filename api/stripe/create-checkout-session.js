// POST /api/stripe/create-checkout-session
// Body: { plan: 'personal'|'clinic'|'addon_mini'|'addon_standard'|'addon_plus' }
// Auth: Authorization: Bearer <supabase access token>
// personal/clinic → mode:subscription、addon_* → mode:payment（one-time）
// Stripe secret key / service_role key はサーバー側環境変数のみ。フロントには出さない。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

// plan key → { env: price env var, mode, tokens (add-on grant; subscriptions grant via invoice webhook) }
const PLANS = {
  personal:       { env: 'STRIPE_PRICE_PERSONAL_MONTHLY', mode: 'subscription' },
  clinic:         { env: 'STRIPE_PRICE_CLINIC_MONTHLY',   mode: 'subscription' },
  addon_mini:     { env: 'STRIPE_PRICE_ADDON_MINI',       mode: 'payment', tokens: 20 },
  addon_standard: { env: 'STRIPE_PRICE_ADDON_STANDARD',   mode: 'payment', tokens: 100 },
  addon_plus:     { env: 'STRIPE_PRICE_ADDON_PLUS',       mode: 'payment', tokens: 300 }
};
// 旧プラン名の互換（表示・新規導線では使用しない）
const LEGACY_ALIAS = { sketch: 'personal', studio: 'clinic' };

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).json({ error: 'method_not_allowed' }); return; }
  try {
    const stripeKey = process.env.STRIPE_SECRET_KEY;
    const supaUrl = process.env.SUPABASE_URL;
    const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!stripeKey || !supaUrl || !srKey) { res.status(500).json({ error: 'server_not_configured' }); return; }

    const jwt = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!jwt) { res.status(401).json({ error: 'unauthorized' }); return; }
    const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });
    const { data: userData, error: userErr } = await admin.auth.getUser(jwt);
    if (userErr || !userData || !userData.user) { res.status(401).json({ error: 'unauthorized' }); return; }
    const user = userData.user;

    const body = req.body || {};
    let plan = String(body.plan || '').toLowerCase();
    if (LEGACY_ALIAS[plan]) plan = LEGACY_ALIAS[plan];
    const conf = PLANS[plan];
    const priceId = conf && process.env[conf.env];
    if (!conf || !priceId) { res.status(400).json({ error: 'price_not_configured' }); return; }

    const stripe = Stripe(stripeKey);

    // billing_customers から既存の Stripe customer を取得（なければ作成して保存）
    let customerId = null;
    const bc = await admin.from('billing_customers')
      .select('stripe_customer_id').eq('user_id', user.id).maybeSingle();
    if (bc.data && bc.data.stripe_customer_id) customerId = bc.data.stripe_customer_id;
    if (!customerId) {
      const customer = await stripe.customers.create({
        email: user.email,
        metadata: { supabase_user_id: user.id }
      });
      customerId = customer.id;
      const up = await admin.from('billing_customers').upsert(
        { user_id: user.id, stripe_customer_id: customerId, updated_at: new Date().toISOString() },
        { onConflict: 'user_id' });
      if (up.error) console.error('[checkout] billing_customers upsert failed', up.error);
    }

    const appUrl = process.env.NEXT_PUBLIC_APP_URL || ('https://' + req.headers.host);
    const params = {
      mode: conf.mode,
      customer: customerId,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: appUrl + '/caseflow_studio_v96.html?checkout=success',
      cancel_url: appUrl + '/caseflow_studio_v96.html?checkout=cancel',
      metadata: { supabase_user_id: user.id, plan: plan, tokens: String(conf.tokens || 0) },
      allow_promotion_codes: true
    };
    if (conf.mode === 'subscription') {
      params.subscription_data = { metadata: { supabase_user_id: user.id, plan: plan } };
    }
    const session = await stripe.checkout.sessions.create(params);

    res.status(200).json({ url: session.url });
  } catch (e) {
    console.error('[stripe checkout] error', e);
    res.status(500).json({ error: 'internal_error' });
  }
};
