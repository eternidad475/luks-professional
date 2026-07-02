// POST /api/stripe/create-checkout-session
// Body: { plan: 'sketch'|'studio', interval: 'month'|'year' }
// Auth: Authorization: Bearer <supabase access token>
// Stripe secret key / service_role key はサーバー側環境変数のみ。フロントには出さない。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

const PRICE_ENV = {
  'sketch:month': 'STRIPE_PRICE_SKETCH_MONTHLY',
  'sketch:year':  'STRIPE_PRICE_SKETCH_ANNUAL',
  'studio:month': 'STRIPE_PRICE_STUDIO_MONTHLY',
  'studio:year':  'STRIPE_PRICE_STUDIO_ANNUAL'
};

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
    const plan = String(body.plan || '').toLowerCase();
    const interval = body.interval === 'year' ? 'year' : 'month';
    const envName = PRICE_ENV[plan + ':' + interval];
    const priceId = envName && process.env[envName];
    if (!priceId) { res.status(400).json({ error: 'price_not_configured' }); return; }

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
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      customer: customerId,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: appUrl + '/caseflow_studio_v96.html?checkout=success',
      cancel_url: appUrl + '/caseflow_studio_v96.html?checkout=cancel',
      subscription_data: { metadata: { supabase_user_id: user.id, plan: plan } },
      metadata: { supabase_user_id: user.id, plan: plan },
      allow_promotion_codes: true
    });

    res.status(200).json({ url: session.url });
  } catch (e) {
    console.error('[stripe checkout] error', e);
    res.status(500).json({ error: 'internal_error' });
  }
};
