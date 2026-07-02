// POST /api/stripe/webhook
// Stripe Webhook 受信。必ず raw body で署名検証し、stripe_event_id で二重処理を防止する。
// トークン残高・サブスク状態の「正」は本Webhookが更新する（フロント反映は表示のみ）。

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

// Vercel Node functions: req.body に触れる前にストリームから raw を読む
async function rawBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(typeof c === 'string' ? Buffer.from(c) : c);
  return Buffer.concat(chunks);
}

const PLAN_TOKENS = { sketch: 100, studio: 500 };

function planFromPriceId(priceId) {
  if (!priceId) return null;
  if (priceId === process.env.STRIPE_PRICE_SKETCH_MONTHLY || priceId === process.env.STRIPE_PRICE_SKETCH_ANNUAL) return 'sketch';
  if (priceId === process.env.STRIPE_PRICE_STUDIO_MONTHLY || priceId === process.env.STRIPE_PRICE_STUDIO_ANNUAL) return 'studio';
  return null;
}
function isAnnualPrice(priceId) {
  return priceId === process.env.STRIPE_PRICE_SKETCH_ANNUAL || priceId === process.env.STRIPE_PRICE_STUDIO_ANNUAL;
}
function ts(sec) { return sec ? new Date(sec * 1000).toISOString() : null; }

module.exports = async (req, res) => {
  if (req.method !== 'POST') { res.status(405).send('method_not_allowed'); return; }
  const stripeKey = process.env.STRIPE_SECRET_KEY;
  const whSecret = process.env.STRIPE_WEBHOOK_SECRET;
  const supaUrl = process.env.SUPABASE_URL;
  const srKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!stripeKey || !whSecret || !supaUrl || !srKey) { res.status(500).send('server_not_configured'); return; }

  const stripe = Stripe(stripeKey);
  let event;
  try {
    const raw = await rawBody(req);
    event = stripe.webhooks.constructEvent(raw, req.headers['stripe-signature'], whSecret);
  } catch (e) {
    console.error('[webhook] signature verification failed', e.message);
    res.status(400).send('invalid_signature');
    return;
  }

  const admin = createClient(supaUrl, srKey, { auth: { persistSession: false } });

  // ---- 冪等性: stripe_event_id unique。既処理なら 200 で即返す ----
  const ins = await admin.from('billing_events').insert({
    stripe_event_id: event.id,
    event_type: event.type,
    payload: { id: event.id, type: event.type, object: (event.data && event.data.object && event.data.object.id) || null }
  });
  if (ins.error) {
    if (String(ins.error.code) === '23505') { res.status(200).send('duplicate_skipped'); return; }
    console.error('[webhook] billing_events insert failed', ins.error);
    // イベント記録に失敗しても処理は続行（テーブル未作成時などは処理だけ通す）
  }

  async function userIdFromCustomer(customerId) {
    if (!customerId) return null;
    const r = await admin.from('billing_customers')
      .select('user_id').eq('stripe_customer_id', customerId).maybeSingle();
    return (r.data && r.data.user_id) || null;
  }

  async function upsertSubscription(sub) {
    const priceId = sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].price && sub.items.data[0].price.id;
    const plan = (sub.metadata && sub.metadata.plan) || planFromPriceId(priceId);
    let userId = (sub.metadata && sub.metadata.supabase_user_id) || await userIdFromCustomer(sub.customer);
    if (!userId) { console.error('[webhook] user not resolved for subscription', sub.id); return null; }
    const row = {
      user_id: userId,
      stripe_subscription_id: sub.id,
      stripe_customer_id: sub.customer,
      plan: plan,
      price_id: priceId || null,
      status: sub.status,
      current_period_start: ts(sub.current_period_start),
      current_period_end: ts(sub.current_period_end),
      cancel_at_period_end: !!sub.cancel_at_period_end,
      updated_at: new Date().toISOString()
    };
    const up = await admin.from('billing_subscriptions').upsert(row, { onConflict: 'stripe_subscription_id' });
    if (up.error) console.error('[webhook] billing_subscriptions upsert failed', up.error);
    return { userId, plan, priceId };
  }

  async function grantTokens(userId, amount, reason, idemKey) {
    if (!userId || !amount) return;
    // 残高更新 + 台帳記録（idempotency_key unique で二重付与防止）
    const prof = await admin.from('profiles').select('tokens_remaining').eq('id', userId).single();
    if (prof.error) { console.error('[webhook] profile fetch failed', prof.error); return; }
    const newBal = (prof.data.tokens_remaining || 0) + amount;
    const led = await admin.from('token_ledger').insert({
      user_id: userId, delta: amount, reason: reason, balance_after: newBal,
      status: 'confirmed', provider: 'stripe', idempotency_key: idemKey
    });
    if (led.error) {
      if (String(led.error.code) === '23505') { console.log('[webhook] grant already applied', idemKey); return; }
      console.error('[webhook] ledger insert failed', led.error); return;
    }
    const up = await admin.from('profiles').update({ tokens_remaining: newBal }).eq('id', userId);
    if (up.error) console.error('[webhook] balance update failed', up.error);
  }

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const userId = session.metadata && session.metadata.supabase_user_id;
        if (userId && session.customer) {
          const up = await admin.from('billing_customers').upsert(
            { user_id: userId, stripe_customer_id: session.customer, updated_at: new Date().toISOString() },
            { onConflict: 'user_id' });
          if (up.error) console.error('[webhook] billing_customers upsert failed', up.error);
        }
        // subscription の詳細反映は customer.subscription.created / invoice で行う
        break;
      }
      case 'customer.subscription.created':
      case 'customer.subscription.updated': {
        await upsertSubscription(event.data.object);
        break;
      }
      case 'customer.subscription.deleted': {
        const sub = event.data.object;
        const up = await admin.from('billing_subscriptions')
          .update({ status: 'canceled', cancel_at_period_end: false, updated_at: new Date().toISOString() })
          .eq('stripe_subscription_id', sub.id);
        if (up.error) console.error('[webhook] cancel update failed', up.error);
        // 既存トークンは没収しない（初期方針）。次回付与は invoice が来なくなるため自然停止。
        break;
      }
      case 'invoice.payment_succeeded': {
        const inv = event.data.object;
        const line = inv.lines && inv.lines.data && inv.lines.data[0];
        const priceId = line && line.price && line.price.id;
        const plan = planFromPriceId(priceId);
        const userId = await userIdFromCustomer(inv.customer);
        if (plan && userId) {
          const monthly = PLAN_TOKENS[plan] || 0;
          // 年額は12ヶ月分を一括付与（初期実装。返金時の扱いは docs 参照。月次ドリップ化は Phase 2.1）
          const amount = isAnnualPrice(priceId) ? monthly * 12 : monthly;
          const reason = isAnnualPrice(priceId) ? 'subscription_annual_grant' : 'subscription_monthly_grant';
          await grantTokens(userId, amount, reason, 'stripe:' + event.id);
        } else {
          console.log('[webhook] invoice without known plan/user', inv.id, priceId);
        }
        break;
      }
      case 'invoice.payment_failed': {
        const inv = event.data.object;
        if (inv.subscription) {
          const up = await admin.from('billing_subscriptions')
            .update({ status: 'past_due', updated_at: new Date().toISOString() })
            .eq('stripe_subscription_id', inv.subscription);
          if (up.error) console.error('[webhook] past_due update failed', up.error);
        }
        // アプリ側は警告表示のみ（即時利用制限はしない）
        break;
      }
      default:
        break;
    }
    // 処理完了マーク
    await admin.from('billing_events')
      .update({ processed_at: new Date().toISOString() })
      .eq('stripe_event_id', event.id);
    res.status(200).send('ok');
  } catch (e) {
    console.error('[webhook] handler error', event.type, e);
    // Stripe に再送させる
    res.status(500).send('handler_error');
  }
};
