// POST /api/stripe/create-portal-session
// Auth: Authorization: Bearer <supabase access token>
// Stripe Customer Portal（解約・カード変更・領収書）への遷移URLを返す。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

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

    const bc = await admin.from('billing_customers')
      .select('stripe_customer_id').eq('user_id', userData.user.id).maybeSingle();
    const customerId = bc.data && bc.data.stripe_customer_id;
    if (!customerId) { res.status(404).json({ error: 'no_customer' }); return; }

    const stripe = Stripe(stripeKey);
    const appUrl = process.env.NEXT_PUBLIC_APP_URL || ('https://' + req.headers.host);
    const session = await stripe.billingPortal.sessions.create({
      customer: customerId,
      return_url: appUrl + '/caseflow_studio_v96.html'
    });

    res.status(200).json({ url: session.url });
  } catch (e) {
    console.error('[stripe portal] error', e);
    res.status(500).json({ error: 'internal_error' });
  }
};
