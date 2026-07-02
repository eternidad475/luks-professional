-- ============================================================
-- Phase 2 — migration 6: 複数トークン消費 + 失敗時返却
-- migration 5 適用済み前提の【追加】migration（5 の書き換えではない）。
-- 消費ルール変更: Visual Simulation / Morphing Video = 1回 2 tokens。
-- 既存 consume_token()（1消費）は互換のため残す（新フロントは consume_tokens を使用）。
-- ============================================================

-- ------------------------------------------------------------
-- 1) consume_tokens(p_amount, p_reason): 原子的な複数トークン消費
--    戻り値に ledger_id を含め、失敗時返却（下記2）の対象を特定できるようにする
-- ------------------------------------------------------------
create or replace function public.consume_tokens(p_amount integer default 2, p_reason text default 'generation')
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_rem integer;
  v_id  bigint;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;
  if p_amount is null or p_amount < 1 or p_amount > 10 then
    return jsonb_build_object('ok', false, 'reason', 'invalid_amount');
  end if;

  update public.profiles
     set tokens_remaining = tokens_remaining - p_amount
   where id = v_uid
     and tokens_remaining >= p_amount
   returning tokens_remaining into v_rem;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'insufficient');
  end if;

  insert into public.token_ledger (user_id, delta, reason, balance_after, status)
  values (v_uid, -p_amount, coalesce(p_reason,'generation'), v_rem, 'confirmed')
  returning id into v_id;

  return jsonb_build_object('ok', true, 'balance', v_rem, 'ledger_id', v_id);
end;
$$;

revoke execute on function public.consume_tokens(integer, text) from public, anon;
grant  execute on function public.consume_tokens(integer, text) to authenticated;

-- ------------------------------------------------------------
-- 2) refund_generation_tokens(p_ledger_id): 生成失敗時の返却
--    悪用防止:
--      - 本人の消費行のみ / delta < 0 のみ
--      - reason が generation / morphing_video 系のみ
--      - 消費から15分以内のみ
--      - idempotency_key 'refund:<ledger_id>' unique で二重返却防止
-- ------------------------------------------------------------
create or replace function public.refund_generation_tokens(p_ledger_id bigint)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_row public.token_ledger%rowtype;
  v_bal integer;
  v_amount integer;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  select * into v_row from public.token_ledger
   where id = p_ledger_id and user_id = v_uid;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'not_found');
  end if;
  if v_row.delta >= 0 then
    return jsonb_build_object('ok', false, 'reason', 'not_a_consumption');
  end if;
  if v_row.reason is null or v_row.reason not in ('generation','morphing_video','regeneration') then
    return jsonb_build_object('ok', false, 'reason', 'not_refundable_reason');
  end if;
  if v_row.created_at < now() - interval '15 minutes' then
    return jsonb_build_object('ok', false, 'reason', 'too_old');
  end if;
  if exists(select 1 from public.token_ledger where idempotency_key = 'refund:' || p_ledger_id) then
    return jsonb_build_object('ok', false, 'reason', 'already_refunded');
  end if;

  v_amount := -v_row.delta;

  update public.profiles
     set tokens_remaining = tokens_remaining + v_amount
   where id = v_uid
   returning tokens_remaining into v_bal;

  insert into public.token_ledger (user_id, delta, reason, balance_after, status, idempotency_key)
  values (v_uid, v_amount, 'generation_refund', v_bal, 'confirmed', 'refund:' || p_ledger_id)
  on conflict (idempotency_key) do nothing;

  return jsonb_build_object('ok', true, 'refunded', v_amount, 'balance', v_bal);
end;
$$;

revoke execute on function public.refund_generation_tokens(bigint) from public, anon;
grant  execute on function public.refund_generation_tokens(bigint) to authenticated;
