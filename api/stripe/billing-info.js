// POST /api/stripe/billing-info
// Auth: Authorization: Bearer <supabase access token>
// 返却: { paymentMethod: {brand,last4,expMonth,expYear}|null, invoices: [...] }
// 支払い方法サマリ（カード番号そのものは扱わず brand + 下4桁のみ）と請求履歴を
// Stripe から取得して返す。Stripe secret key はサーバー側のみ。フロントには出さない。
// 未契約（Stripe customer 無し）のユーザーは空データを 200 で返す（エラーにしない）。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

function cardSummary(pm) {
  if (!pm || !pm.card) return null;
  return {
    brand: pm.card.brand || null,
    last4: pm.card.last4 || null,
    expMonth: pm.card.exp_month || null,
    expYear: pm.card.exp_year || null
  };
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).json({ error: 'method_not_allowed' }); return; }
  try {
    const stripeKey = process.env.STRIPE_SECRET_KEY;
    const supaUrl = process.env.SUPABASE_URL;
    const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!stripeKey || !supaUrl || !srKey) {
      const missing = [
        !stripeKey && 'STRIPE_SECRET_KEY',
        !supaUrl && 'SUPABASE_URL',
        !srKey && 'SUPABASE_SERVICE_ROLE_KEY'
      ].filter(Boolean);
      res.status(500).json({ error: 'server_not_configured', missing: missing });
      return;
    }

    const jwt = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!jwt) { res.status(401).json({ error: 'unauthorized' }); return; }
    const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });
    const { data: userData, error: userErr } = await admin.auth.getUser(jwt);
    if (userErr || !userData || !userData.user) { res.status(401).json({ error: 'unauthorized' }); return; }

    const bc = await admin.from('billing_customers')
      .select('stripe_customer_id').eq('user_id', userData.user.id).maybeSingle();
    const customerId = bc.data && bc.data.stripe_customer_id;
    if (!customerId) { res.status(200).json({ paymentMethod: null, invoices: [] }); return; }

    const stripe = Stripe(stripeKey);

    // ---- 支払い方法サマリ（default → なければ最新のカード1件）----
    let paymentMethod = null;
    try {
      const cust = await stripe.customers.retrieve(customerId);
      const defId = cust && cust.invoice_settings && cust.invoice_settings.default_payment_method;
      if (defId) {
        const pm = await stripe.paymentMethods.retrieve(String(defId));
        paymentMethod = cardSummary(pm);
      }
      if (!paymentMethod) {
        const pms = await stripe.paymentMethods.list({ customer: customerId, type: 'card', limit: 1 });
        if (pms && pms.data && pms.data[0]) paymentMethod = cardSummary(pms.data[0]);
      }
    } catch (e) {
      console.error('[billing-info] payment method fetch failed', e && e.message);
    }

    // ---- 請求履歴（直近6件・領収書リンク付き）----
    let invoices = [];
    try {
      const inv = await stripe.invoices.list({ customer: customerId, limit: 6 });
      invoices = (inv.data || []).map(function (i) {
        return {
          number: i.number || null,
          created: i.created || null,
          amount: (i.amount_paid != null ? i.amount_paid : i.amount_due) || 0,
          currency: i.currency || null,
          status: i.status || null,
          hostedUrl: i.hosted_invoice_url || null,
          pdf: i.invoice_pdf || null
        };
      });
    } catch (e) {
      console.error('[billing-info] invoices fetch failed', e && e.message);
    }

    res.status(200).json({ paymentMethod: paymentMethod, invoices: invoices });
  } catch (e) {
    console.error('[stripe billing-info] error', e);
    res.status(500).json({ error: 'internal_error' });
  }
};
