// POST /api/stripe/create-portal-session
// Auth: Authorization: Bearer <supabase access token>
// Body (optional): { flow: 'change_plan' | 'payment_method' | 'cancel' }
//   - なし / 'manage'        → 通常の Stripe Customer Portal（請求履歴・領収書・カード・解約すべて）
//   - 'change_plan'          → subscription_update フロー（プラン変更画面に直行）
//   - 'payment_method'       → payment_method_update フロー（カード変更画面に直行）
//   - 'cancel'               → subscription_cancel フロー（解約画面に直行）
// Stripe secret key はサーバー側環境変数のみ。フロントには出さない。
// 解約は即時停止ではなく Stripe 標準の「請求期間終了時に停止（cancel_at_period_end）」。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).json({ error: 'method_not_allowed' }); return; }
  try {
    const stripeKey = process.env.STRIPE_SECRET_KEY;
    const supaUrl = process.env.SUPABASE_URL;
    const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!stripeKey || !supaUrl || !srKey) {
      // 診断: 値は出力しない。存在有無のみ。
      const missing = [
        !stripeKey && 'STRIPE_SECRET_KEY',
        !supaUrl && 'SUPABASE_URL',
        !srKey && 'SUPABASE_SERVICE_ROLE_KEY'
      ].filter(Boolean);
      console.error('[portal] server_not_configured', JSON.stringify({ missing: missing, vercelEnv: process.env.VERCEL_ENV || null }));
      res.status(500).json({ error: 'server_not_configured', missing: missing });
      return;
    }

    const jwt = String(req.headers.authorization || '').replace(/^Bearer\s+/i, '');
    if (!jwt) { res.status(401).json({ error: 'unauthorized' }); return; }
    const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });
    const { data: userData, error: userErr } = await admin.auth.getUser(jwt);
    if (userErr || !userData || !userData.user) { res.status(401).json({ error: 'unauthorized' }); return; }
    const userId = userData.user.id;

    const bc = await admin.from('billing_customers')
      .select('stripe_customer_id').eq('user_id', userId).maybeSingle();
    const customerId = bc.data && bc.data.stripe_customer_id;
    if (!customerId) { res.status(404).json({ error: 'no_customer' }); return; }

    const stripe = Stripe(stripeKey);
    const appUrl = process.env.NEXT_PUBLIC_APP_URL || ('https://' + req.headers.host);
    // Portal から戻ったら Account/Billing 画面へ復帰（意図しない Studio 画面に飛ばさない）
    const returnUrl = appUrl + '/caseflow_studio_v96.html?billing=1';

    const flow = String((req.body && req.body.flow) || '').toLowerCase();
    const params = { customer: customerId, return_url: returnUrl };

    if (flow === 'payment_method') {
      params.flow_data = { type: 'payment_method_update' };
    } else if (flow === 'change_plan' || flow === 'cancel') {
      // subscription_update / subscription_cancel は対象 subscription が必須。
      const bs = await admin.from('billing_subscriptions')
        .select('stripe_subscription_id,status')
        .eq('user_id', userId)
        .in('status', ['active', 'trialing', 'past_due'])
        .order('updated_at', { ascending: false }).limit(1).maybeSingle();
      const subId = bs.data && bs.data.stripe_subscription_id;
      if (!subId) { res.status(409).json({ error: 'no_subscription' }); return; }
      if (flow === 'change_plan') {
        params.flow_data = { type: 'subscription_update', subscription_update: { subscription: subId } };
      } else {
        // 解約は cancel_at_period_end（期末停止）。即時停止ではない。
        params.flow_data = { type: 'subscription_cancel', subscription_cancel: { subscription: subId } };
      }
    }

    let session;
    try {
      session = await stripe.billingPortal.sessions.create(params);
    } catch (e) {
      // flow が Portal 設定で未有効な場合（例: subscription_update に商品未設定）は
      // 汎用ポータルにフォールバックして必ず遷移できるようにする。
      if (params.flow_data) {
        console.error('[portal] flow_data rejected, falling back to plain portal', flow, e && e.message);
        session = await stripe.billingPortal.sessions.create({ customer: customerId, return_url: returnUrl });
      } else {
        throw e;
      }
    }

    res.status(200).json({ url: session.url });
  } catch (e) {
    console.error('[stripe portal] error', e);
    res.status(500).json({ error: 'internal_error' });
  }
};
