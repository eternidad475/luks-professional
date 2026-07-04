-- Admin-only Stripe revenue summary for the admin dashboard (REVENUE card).
--
-- Returns reference (概算/estimate) figures only — NOT an accounting statement.
-- Security: SECURITY DEFINER + is_admin() gate (role in developer/admin);
-- execute granted to authenticated only (self-gated), revoked from anon/public.
-- Data source: current-month amounts persisted by the Stripe webhook into
-- billing_events.payload (kind/amount/currency) + MRR from active
-- billing_subscriptions. No Stripe secret key is involved — runs entirely in-DB.
--
-- Applied live 2026-07-14 (project nuolihmfdjzofporhwkp). Verified: admin →
-- summary jsonb; non-admin → 42501; anon → no execute grant.

create or replace function public.admin_revenue_summary()
returns jsonb
language plpgsql
security definer
set search_path to 'public'
as $function$
declare
  v jsonb;
  m_start timestamptz := date_trunc('month', now());
  sub_month numeric := 0;
  addon_month numeric := 0;
  refund_month numeric := 0;
  pay_count int := 0;
  mrr numeric := 0;
  gross numeric := 0;
  net numeric := 0;
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;

  -- Current-month revenue from amounts persisted by the Stripe webhook
  -- (payload.kind in subscription/addon/refund, payload.amount in JPY minor unit = yen).
  select
    coalesce(sum(case when payload->>'kind'='subscription' then coalesce((payload->>'amount')::numeric,0) else 0 end),0),
    coalesce(sum(case when payload->>'kind'='addon'        then coalesce((payload->>'amount')::numeric,0) else 0 end),0),
    coalesce(sum(case when payload->>'kind'='refund'       then coalesce((payload->>'amount')::numeric,0) else 0 end),0),
    count(*) filter (where payload->>'kind' in ('subscription','addon'))
  into sub_month, addon_month, refund_month, pay_count
  from public.billing_events
  where created_at >= m_start
    and payload ? 'kind';

  -- MRR from active subscriptions (known JPY plan prices: Sketch 1500 / Clinic Studio 5000)
  select coalesce(sum(case bs.plan
            when 'personal' then 1500
            when 'clinic'   then 5000
            else 0 end),0)
    into mrr
  from public.billing_subscriptions bs
  where bs.status in ('active','trialing');

  gross := sub_month + addon_month;
  -- Net is a rough estimate after ~3.6% Stripe JP card fee; not an accounting figure.
  net := round((gross - refund_month) * (1 - 0.036));

  v := jsonb_build_object(
    'currency','JPY',
    'month',        to_char(m_start at time zone 'Asia/Tokyo','YYYY-MM'),
    'gross_month',  gross,
    'sub_month',    sub_month,
    'addon_month',  addon_month,
    'refund_month', refund_month,
    'payment_count',pay_count,
    'mrr',          mrr,
    'net_estimate', net,
    'generated_at', to_char(now() at time zone 'Asia/Tokyo','YYYY-MM-DD HH24:MI')
  );
  return v;
end;
$function$;

revoke all on function public.admin_revenue_summary() from public;
revoke all on function public.admin_revenue_summary() from anon;
grant execute on function public.admin_revenue_summary() to authenticated;
