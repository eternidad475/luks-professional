-- ============================================================
-- Migration 10: トークン付与ポリシー変更（2026-07-02 確定）
--
-- 新方針:
--   Trial               = 10 tokens（変更なし・claim_trial_tokens は元々10）
--   Invitee Grant       = 10 tokens（100 → 10）
--   Inviter Bonus       =  5 tokens（100 → 5）
--   Personal monthly    = 100 tokens（api/stripe/webhook.js — 既に100・変更なし）
--   Clinic monthly      = 500 tokens（api/stripe/webhook.js — 既に500・変更なし）
--
-- 重複防止:
--   * Trial と Invitee Grant は重複付与しない
--     - accept_invite_code: 承認時に trial_tokens_granted = true を立てる
--     - claim_trial_tokens: invitee grant 受領済みなら already_granted を返す
--   * 自分自身の招待コードは承認不可（reason='self_invite'）
--   * inviter bonus の一回性は idempotency_key 'inviter:<invite_id>:<invitee>' で担保（既存）
--
-- 含まないもの:
--   * 過剰付与済みユーザーへの補正 ledger（ユーザー固有の一回きりデータ修正のため
--     migration には含めず、別途実行・記録。reason='invite_grant_policy_adjustment'）
--   * token_ledger 過去行の編集（監査履歴のため一切行わない）
-- ============================================================

-- ------------------------------------------------------------
-- 1) invite_codes の default 変更（invitee 100→10 / inviter 100→5）
-- ------------------------------------------------------------
alter table public.invite_codes alter column token_grant_invitee set default 10;
alter table public.invite_codes alter column token_grant_inviter set default 5;

-- ------------------------------------------------------------
-- 2) 既存未使用コードの旧既定値（100/100）を新既定値へ更新
--    使用済みコード（used_count > 0）の履歴値は改ざんしない
-- ------------------------------------------------------------
update public.invite_codes
   set token_grant_invitee = 10,
       token_grant_inviter = 5,
       updated_at = now()
 where used_count = 0
   and token_grant_invitee = 100
   and token_grant_inviter = 100;

-- ------------------------------------------------------------
-- 3) admin_create_invite_code: パラメータ default を 10 / 5 に（body 不変）
-- ------------------------------------------------------------
create or replace function public.admin_create_invite_code(
  p_code text default null,
  p_invited_email text default null,
  p_role text default 'dentist',
  p_workspace_type text default 'personal',
  p_token_grant_invitee integer default 10,
  p_token_grant_inviter integer default 5,
  p_max_uses integer default 1,
  p_expires_at timestamptz default null
) returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_uid  uuid := auth.uid();
  v_code text;
  v_id   uuid;
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  v_code := coalesce(nullif(trim(p_code),''),
    'CF-' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,8)));

  insert into public.invite_codes
    (code, invited_email, invited_by, workspace_type, role,
     token_grant_invitee, token_grant_inviter, max_uses, expires_at)
  values
    (v_code, nullif(trim(p_invited_email),''), v_uid, p_workspace_type, p_role,
     p_token_grant_invitee, p_token_grant_inviter, greatest(1,p_max_uses), p_expires_at)
  returning id into v_id;

  insert into public.admin_audit_logs (admin_user_id, action, target_type, target_id, metadata)
  values (v_uid, 'invite_code_created', 'invite_code', v_id::text,
          jsonb_build_object('code', v_code, 'role', p_role, 'invitee_grant', p_token_grant_invitee));

  return jsonb_build_object('ok', true, 'id', v_id, 'code', v_code);
end;
$$;
revoke execute on function public.admin_create_invite_code(text,text,text,text,integer,integer,integer,timestamptz) from public, anon;
grant  execute on function public.admin_create_invite_code(text,text,text,text,integer,integer,integer,timestamptz) to authenticated;

-- ------------------------------------------------------------
-- 4) accept_invite_code v3:
--    - 承認時に trial_tokens_granted = true（Trial との重複付与防止）
--    - 自分自身の招待コードは承認不可（reason='self_invite'）
--    （付与量は invite_codes 行の値をそのまま使用 — 2) 以降の新規コードは 10/5）
-- ------------------------------------------------------------
create or replace function public.accept_invite_code(p_code text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_uid       uuid := auth.uid();
  v_email     text;
  v_confirmed timestamptz;
  v_code      text;
  v_inv       public.invite_codes%rowtype;
  v_bal       integer;
  v_inviter_bal integer;
  v_ws        uuid;
  v_inviter_ws uuid;
begin
  if v_uid is null then
    return jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  end if;

  select email, email_confirmed_at into v_email, v_confirmed
    from auth.users where id = v_uid;
  if v_confirmed is null then
    return jsonb_build_object('ok', false, 'reason', 'email_unconfirmed');
  end if;

  v_code := upper(trim(coalesce(p_code, '')));
  if v_code = '' then
    return jsonb_build_object('ok', false, 'reason', 'invalid');
  end if;

  select * into v_inv from public.invite_codes
   where upper(code) = v_code
   for update;
  if v_inv.id is null and position('O' in v_code) > 0 then
    select * into v_inv from public.invite_codes
     where upper(code) = replace(v_code, 'O', '0')
     for update;
  end if;

  if v_inv.id is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid');
  end if;
  if v_inv.revoked_at is not null then
    return jsonb_build_object('ok', false, 'reason', 'revoked');
  end if;
  if v_inv.expires_at is not null and v_inv.expires_at <= now() then
    return jsonb_build_object('ok', false, 'reason', 'expired');
  end if;
  if v_inv.invited_email is not null and lower(v_inv.invited_email) <> lower(coalesce(v_email, '')) then
    return jsonb_build_object('ok', false, 'reason', 'email_mismatch');
  end if;
  -- 自分自身への招待は不可（inviter bonus の自己付与防止）
  if v_inv.invited_by is not null and v_inv.invited_by = v_uid then
    return jsonb_build_object('ok', false, 'reason', 'self_invite');
  end if;

  -- 既にこのユーザーが承認済み → 状態修復のみ（後追い再実行を許容・追加付与なし）
  if exists(select 1 from public.invite_redemptions
             where invite_code_id = v_inv.id and invitee_id = v_uid)
     or exists(select 1 from public.token_ledger
                where user_id = v_uid and reason = 'invitee_initial_beta_grant') then
    update public.profiles
       set beta_access = true,
           trial_tokens_granted = true,
           professional_confirmed = true,
           professional_type = coalesce(professional_type, v_inv.role)
     where id = v_uid;
    return jsonb_build_object('ok', true, 'granted', 0, 'note', 'already_granted');
  end if;

  if v_inv.used_count >= v_inv.max_uses then
    return jsonb_build_object('ok', false, 'reason', 'exhausted');
  end if;

  insert into public.invite_redemptions
    (invite_code_id, invitee_id, inviter_id, invitee_tokens, inviter_tokens)
  values
    (v_inv.id, v_uid, v_inv.invited_by, v_inv.token_grant_invitee,
     case when v_inv.invited_by is not null then v_inv.token_grant_inviter else 0 end);

  update public.invite_codes
     set used_count = used_count + 1,
         accepted_by = v_uid,
         accepted_at = now(),
         updated_at = now()
   where id = v_inv.id;

  update public.profiles
     set beta_access = true,
         trial_tokens_granted = true,   -- Invitee Grant は Trial を兼ねる（二重取得防止）
         role = case when role = 'dentist' then v_inv.role else role end,
         professional_confirmed = true,
         professional_type = coalesce(professional_type, v_inv.role),
         tokens_remaining = tokens_remaining + v_inv.token_grant_invitee
   where id = v_uid
   returning tokens_remaining into v_bal;

  select id into v_ws from public.workspaces
   where owner_user_id = v_uid and type = 'personal' and deleted_at is null;
  if v_ws is not null then
    update public.workspaces
       set tokens_remaining = tokens_remaining + v_inv.token_grant_invitee,
           updated_at = now()
     where id = v_ws;
  end if;

  insert into public.token_ledger
    (user_id, workspace_id, delta, reason, balance_after, status, idempotency_key)
  values
    (v_uid, v_ws, v_inv.token_grant_invitee, 'invitee_initial_beta_grant', v_bal,
     'confirmed', 'invitee:' || v_inv.id || ':' || v_uid);

  if v_inv.invited_by is not null and v_inv.token_grant_inviter > 0 then
    update public.profiles
       set tokens_remaining = tokens_remaining + v_inv.token_grant_inviter
     where id = v_inv.invited_by
     returning tokens_remaining into v_inviter_bal;
    if found then
      select id into v_inviter_ws from public.workspaces
       where owner_user_id = v_inv.invited_by and type = 'personal' and deleted_at is null;
      if v_inviter_ws is not null then
        update public.workspaces
           set tokens_remaining = tokens_remaining + v_inv.token_grant_inviter,
               updated_at = now()
         where id = v_inviter_ws;
      end if;
      insert into public.token_ledger
        (user_id, workspace_id, delta, reason, balance_after, status, idempotency_key)
      values
        (v_inv.invited_by, v_inviter_ws, v_inv.token_grant_inviter,
         'inviter_referral_beta_bonus', v_inviter_bal, 'confirmed',
         'inviter:' || v_inv.id || ':' || v_uid)
      on conflict (idempotency_key) do nothing;
    end if;
  end if;

  return jsonb_build_object('ok', true, 'granted', v_inv.token_grant_invitee, 'balance', v_bal);
exception when others then
  return jsonb_build_object('ok', false, 'reason', 'db_error', 'code', sqlstate);
end $$;

revoke execute on function public.accept_invite_code(text) from public, anon;
grant  execute on function public.accept_invite_code(text) to authenticated;

-- ------------------------------------------------------------
-- 5) claim_trial_tokens v2:
--    - Invitee Grant 受領済みユーザーには付与しない（重複防止・逆方向）
--    - token_ledger.workspace_id をスタンプ / workspaces mirror にも加算
--      （2.1b の残高正規化に備える。profiles が引き続き「正」）
-- ------------------------------------------------------------
create or replace function public.claim_trial_tokens()
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
declare
  v_uid uuid := auth.uid();
  v_bal integer;
  v_ws  uuid;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  -- 招待承認で Invitee Grant を受領済みなら Trial は付与しない
  if exists (select 1 from public.token_ledger
              where user_id = v_uid and reason = 'invitee_initial_beta_grant') then
    update public.profiles set trial_tokens_granted = true
     where id = v_uid and trial_tokens_granted = false;
    return jsonb_build_object('ok', false, 'reason', 'already_granted');
  end if;

  update public.profiles
     set trial_tokens_granted = true,
         tokens_remaining = tokens_remaining + 10
   where id = v_uid and trial_tokens_granted = false
   returning tokens_remaining into v_bal;
  if not found then
    return jsonb_build_object('ok', false, 'reason', 'already_granted');
  end if;

  select id into v_ws from public.workspaces
   where owner_user_id = v_uid and type = 'personal' and deleted_at is null;
  if v_ws is not null then
    update public.workspaces
       set tokens_remaining = tokens_remaining + 10,
           updated_at = now()
     where id = v_ws;
  end if;

  insert into public.token_ledger (user_id, workspace_id, delta, reason, balance_after, status, idempotency_key)
  values (v_uid, v_ws, 10, 'trial_grant', v_bal, 'confirmed', 'trial:' || v_uid)
  on conflict (idempotency_key) do nothing;

  return jsonb_build_object('ok', true, 'granted', 10, 'balance', v_bal);
end $$;

revoke execute on function public.claim_trial_tokens() from public, anon;
grant  execute on function public.claim_trial_tokens() to authenticated;

-- ============================================================
-- 適用後の確認（手動）:
--  * 未使用コードの grant 値が 10/5 になっていること
--  * 新規発行コードの default が 10/5 であること
--  * 補正 ledger（invite_grant_policy_adjustment）適用後:
--      profiles.tokens_remaining = personal workspace.tokens_remaining
--      = 各ユーザー最新 token_ledger.balance_after
-- ============================================================
