// POST /api/stripe/webhook
// Stripe Webhook 受信。必ず raw body で署名検証し、stripe_event_id で二重処理を防止する。
// トークン残高・サブスク状態の「正」は本Webhookが更新する（フロント反映は表示のみ）。
// - subscription (personal/clinic): トークン付与は invoice.payment_succeeded 側
// - payment (addon_*): checkout.session.completed で即時付与

const Stripe = require('stripe');
const { createClient } = require('@supabase/supabase-js');

// Vercel Node functions: req.body に触れる前にストリームから raw を読む
async function rawBody(req) {
  const chunks = [];
  for await (const c of req) chunks.push(typeof c === 'string' ? Buffer.from(c) : c);
  return Buffer.concat(chunks);
}

// plan → 月次付与トークン / ledger reason
const SUB_PLANS = {
  personal: { tokens: 100, reason: 'subscription_personal_monthly' },
  clinic:   { tokens: 500, reason: 'subscription_clinic_monthly' }
};
const ADDONS = {
  addon_mini:     { tokens: 20,  reason: 'token_addon_mini' },
  addon_standard: { tokens: 100, reason: 'token_addon_standard' },
  addon_plus:     { tokens: 300, reason: 'token_addon_plus' }
};

function planFromPriceId(priceId) {
  if (!priceId) return null;
  if (priceId === process.env.STRIPE_PRICE_PERSONAL_MONTHLY) return 'personal';
  if (priceId === process.env.STRIPE_PRICE_CLINIC_MONTHLY) return 'clinic';
  // 旧env互換（設定が残っている場合のみ）
  if (priceId === process.env.STRIPE_PRICE_SKETCH_MONTHLY) return 'personal';
  if (priceId === process.env.STRIPE_PRICE_STUDIO_MONTHLY) return 'clinic';
  return null;
}
function ts(sec) { return sec ? new Date(sec * 1000).toISOString() : null; }

// Extract monetary fields for the admin Revenue card (amounts are minor units;
// JPY has no minor unit, so amount is already yen). Returns null for non-revenue events.
function revenueMeta(event) {
  const o = (event.data && event.data.object) || {};
  const t = event.type;
  if (t === 'invoice.payment_succeeded' || t === 'invoice.paid') {
    const reason = String(o.billing_reason || '');
    const kind = reason.indexOf('subscription') === 0 ? 'subscription' : 'invoice';
    const amount = (o.amount_paid != null ? o.amount_paid : o.amount_due) || 0;
    return { kind, amount, currency: o.currency || null, reason: reason || null };
  }
  if (t === 'checkout.session.completed' && o.mode === 'payment') {
    return { kind: 'addon', amount: o.amount_total || 0, currency: o.currency || null,
             plan: (o.metadata && o.metadata.plan) || null };
  }
  if (t === 'charge.refunded') {
    return { kind: 'refund', amount: (o.amount_refunded != null ? o.amount_refunded : (o.amount || 0)), currency: o.currency || null };
  }
  if (t === 'refund.created' || t === 'charge.refund.updated') {
    return { kind: 'refund', amount: o.amount || 0, currency: o.currency || null };
  }
  return null;
}

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
  // payload には金額メタ（kind/amount/currency）も保存し、admin_revenue_summary() が
  // Stripe実額から今月売上・Add-on・返金を集計できるようにする（トークン付与処理には非依存）。
  const payload = { id: event.id, type: event.type, object: (event.data && event.data.object && event.data.object.id) || null };
  const meta = revenueMeta(event);
  if (meta) {
    payload.kind = meta.kind;
    payload.amount = meta.amount;
    payload.currency = meta.currency;
    if (meta.reason) payload.reason = meta.reason;
    if (meta.plan) payload.plan = meta.plan;
  }
  const ins = await admin.from('billing_events').insert({
    stripe_event_id: event.id,
    event_type: event.type,
    payload: payload
  });
  if (ins.error) {
    if (String(ins.error.code) === '23505') { res.status(200).send('duplicate_skipped'); return; }
    console.error('[webhook] billing_events insert failed', ins.error);
  }

  async function userIdFromCustomer(customerId) {
    if (!customerId) return null;
    const r = await admin.from('billing_customers')
      .select('user_id').eq('stripe_customer_id', customerId).maybeSingle();
    return (r.data && r.data.user_id) || null;
  }

  async function upsertSubscription(sub) {
    const priceId = sub.items && sub.items.data && sub.items.data[0] && sub.items.data[0].price && sub.items.data[0].price.id;
    let plan = (sub.metadata && sub.metadata.plan) || planFromPriceId(priceId);
    if (plan === 'sketch') plan = 'personal';
    if (plan === 'studio') plan = 'clinic';
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
        const userId = (session.metadata && session.metadata.supabase_user_id) || await userIdFromCustomer(session.customer);
        if (userId && session.customer) {
          const up = await admin.from('billing_customers').upsert(
            { user_id: userId, stripe_customer_id: session.customer, updated_at: new Date().toISOString() },
            { onConflict: 'user_id' });
          if (up.error) console.error('[webhook] billing_customers upsert failed', up.error);
        }
        if (session.mode === 'payment') {
          // Add-on one-time purchase → 即時付与（idempotency: event id）
          const plan = session.metadata && session.metadata.plan;
          const addon = ADDONS[plan];
          if (addon && userId && session.payment_status === 'paid') {
            await grantTokens(userId, addon.tokens, addon.reason, 'stripe:' + event.id);
          } else if (!addon) {
            console.log('[webhook] payment session without known addon plan', session.id, plan);
          }
        }
        // subscription の詳細反映は customer.subscription.* / invoice 側で行う
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
        // 既存トークンは没収しない。invoice が止まることで次回付与が自然停止。
        break;
      }
      case 'invoice.payment_succeeded': {
        const inv = event.data.object;
        const line = inv.lines && inv.lines.data && inv.lines.data[0];
        const priceId = line && line.price && line.price.id;
        const plan = planFromPriceId(priceId);
        const conf = plan && SUB_PLANS[plan];
        const userId = await userIdFromCustomer(inv.customer);
        if (conf && userId) {
          await grantTokens(userId, conf.tokens, conf.reason, 'stripe:' + event.id);
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
      case 'customer.updated': {
        // Stripe customer ↔ アプリユーザーの紐付けを維持（email 変更等の同期）。
        // 支払い方法サマリは billing-info API が都度 Stripe から取得するため保存不要。
        const cust = event.data.object;
        const userId = (cust.metadata && cust.metadata.supabase_user_id) || await userIdFromCustomer(cust.id);
        if (userId) {
          const up = await admin.from('billing_customers').upsert(
            { user_id: userId, stripe_customer_id: cust.id, updated_at: new Date().toISOString() },
            { onConflict: 'user_id' });
          if (up.error) console.error('[webhook] billing_customers (customer.updated) upsert failed', up.error);
        }
        break;
      }
      default:
        break;
    }
    await admin.from('billing_events')
      .update({ processed_at: new Date().toISOString() })
      .eq('stripe_event_id', event.id);
    res.status(200).send('ok');
  } catch (e) {
    console.error('[webhook] handler error', event.type, e);
    res.status(500).send('handler_error');
  }
};
