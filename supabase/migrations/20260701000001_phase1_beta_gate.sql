-- ============================================================
-- Phase 1 Emergency Beta Gate — migration 1/2 (additive only)
-- 提案段階。適用は Supabase MCP apply_migration / SQL Editor で行う。
-- 既存テーブル・関数・policy を破壊しない（列追加と新規オブジェクトのみ）。
-- 冪等（IF NOT EXISTS / OR REPLACE / DO block guard）。
-- ============================================================

-- ------------------------------------------------------------
-- 1) profiles: role / beta_access（招待制ベータの中核列）
-- ------------------------------------------------------------
alter table public.profiles
  add column if not exists role text not null default 'dentist',
  add column if not exists beta_access boolean not null default false;

do $$ begin
  alter table public.profiles
    add constraint profiles_role_check check (role in
      ('developer','co_developer','owner','admin','dentist','staff','viewer','billing_manager','patient_link_viewer'));
exception when duplicate_object then null; end $$;

-- ------------------------------------------------------------
-- 2) token_ledger: 台帳拡張（全て nullable の additive 変更）
--    reason の語彙（新規追加分）:
--    signup_initial_grant / invitee_initial_beta_grant /
--    inviter_referral_beta_bonus / generation / generation_refund /
--    admin_grant / purchase / subscription_monthly_grant
-- ------------------------------------------------------------
alter table public.token_ledger
  add column if not exists organization_id uuid,
  add column if not exists workspace_id    uuid,
  add column if not exists case_id         uuid,
  add column if not exists generation_id   uuid,
  add column if not exists provider        text,
  add column if not exists model           text,
  add column if not exists status          text default 'confirmed',
  add column if not exists idempotency_key text;

create unique index if not exists token_ledger_idempotency_idx
  on public.token_ledger(idempotency_key) where idempotency_key is not null;

-- ------------------------------------------------------------
-- 3) ロール判定ヘルパー（RLS から使う。SECURITY DEFINER で profiles を参照）
-- ------------------------------------------------------------
create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists(
    select 1 from public.profiles
    where id = (select auth.uid()) and role in ('developer','admin')
  );
$$;

create or replace function public.is_privileged()
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists(
    select 1 from public.profiles
    where id = (select auth.uid()) and role in ('developer','co_developer','admin')
  );
$$;

revoke execute on function public.is_admin()      from public, anon;
revoke execute on function public.is_privileged() from public, anon;
grant  execute on function public.is_admin()      to authenticated;
grant  execute on function public.is_privileged() to authenticated;

-- ------------------------------------------------------------
-- 4) invite_codes（招待コード）
-- ------------------------------------------------------------
create table if not exists public.invite_codes (
  id                  uuid primary key default gen_random_uuid(),
  code                text not null unique,
  invited_email       text,
  invited_by          uuid references auth.users(id) on delete set null,
  workspace_type      text not null default 'personal',   -- personal / developer / clinic / group
  role                text not null default 'dentist',
  token_grant_invitee integer not null default 100,
  token_grant_inviter integer not null default 100,
  max_uses            integer not null default 1,
  used_count          integer not null default 0,
  expires_at          timestamptz,
  accepted_by         uuid references auth.users(id) on delete set null,  -- 最新の承認者
  accepted_at         timestamptz,
  revoked_at          timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists invite_codes_code_idx on public.invite_codes(code);

-- 承認履歴（同一ユーザー×同一コードの重複使用防止・inviterボーナス1回制約）
create table if not exists public.invite_redemptions (
  id             uuid primary key default gen_random_uuid(),
  invite_code_id uuid not null references public.invite_codes(id) on delete cascade,
  invitee_id     uuid not null references auth.users(id) on delete cascade,
  inviter_id     uuid references auth.users(id) on delete set null,
  invitee_tokens integer not null default 0,
  inviter_tokens integer not null default 0,
  created_at     timestamptz not null default now(),
  unique (invite_code_id, invitee_id)
);

alter table public.invite_codes       enable row level security;
alter table public.invite_redemptions enable row level security;

-- 管理者のみ閲覧・作成・更新（一般ユーザーは RPC 経由でのみ承認）
drop policy if exists "admin read invite codes"   on public.invite_codes;
drop policy if exists "admin insert invite codes" on public.invite_codes;
drop policy if exists "admin update invite codes" on public.invite_codes;
create policy "admin read invite codes"   on public.invite_codes for select using (public.is_admin());
create policy "admin insert invite codes" on public.invite_codes for insert with check (public.is_admin());
create policy "admin update invite codes" on public.invite_codes for update using (public.is_admin()) with check (public.is_admin());

drop policy if exists "admin read redemptions" on public.invite_redemptions;
create policy "admin read redemptions" on public.invite_redemptions for select using (public.is_admin());

-- ------------------------------------------------------------
-- 5) feedback_items（ユーザーは insert のみ / 管理者のみ select・update）
-- ------------------------------------------------------------
create table if not exists public.feedback_items (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  organization_id uuid,
  workspace_id    uuid,
  case_id         uuid,
  asset_id        uuid,
  category        text not null default 'Other' check (category in
    ('Bug','UI Issue','Generation Quality','Clinical Accuracy','Morphing Quality','Account','Billing','Security','Other')),
  severity        text not null default 'normal' check (severity in ('low','normal','high','critical')),
  message         text not null check (char_length(message) between 1 and 4000),
  page_path       text,
  user_agent      text,
  screenshot_url  text,
  status          text not null default 'new' check (status in ('new','triaged','in_progress','resolved','archived')),
  ai_summary      text,          -- 将来の CaseFlow Intelligence™ / sanitized issue 用
  admin_notes     text,
  created_at      timestamptz not null default now(),
  resolved_at     timestamptz
);
create index if not exists feedback_items_status_idx on public.feedback_items(status, created_at desc);

alter table public.feedback_items enable row level security;

drop policy if exists "user insert own feedback" on public.feedback_items;
drop policy if exists "admin read feedback"      on public.feedback_items;
drop policy if exists "admin update feedback"    on public.feedback_items;
-- 一般ユーザー: insert のみ（select policy を作らない = select 不可）
create policy "user insert own feedback" on public.feedback_items
  for insert with check ((select auth.uid()) = user_id);
create policy "admin read feedback"   on public.feedback_items for select using (public.is_admin());
create policy "admin update feedback" on public.feedback_items for update using (public.is_admin()) with check (public.is_admin());

-- ------------------------------------------------------------
-- 6) admin_audit_logs（管理操作の監査ログ）
-- ------------------------------------------------------------
create table if not exists public.admin_audit_logs (
  id            uuid primary key default gen_random_uuid(),
  admin_user_id uuid not null references auth.users(id) on delete cascade,
  action        text not null,       -- invite_code_created / invite_code_revoked / tokens_granted / feedback_viewed / feedback_updated / ...
  target_type   text,
  target_id     text,
  metadata      jsonb,
  created_at    timestamptz not null default now()
);
create index if not exists admin_audit_logs_created_idx on public.admin_audit_logs(created_at desc);

alter table public.admin_audit_logs enable row level security;
drop policy if exists "admin read audit logs" on public.admin_audit_logs;
create policy "admin read audit logs" on public.admin_audit_logs for select using (public.is_admin());
-- insert は SECURITY DEFINER 関数からのみ（policy なし = 直接 insert 不可）

-- ------------------------------------------------------------
-- 7) accept_invite_code(code): 招待承認 + 100/100 トークン付与（原子的）
-- ------------------------------------------------------------
create or replace function public.accept_invite_code(p_code text)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  v_uid     uuid := auth.uid();
  v_email   text;
  v_inv     public.invite_codes%rowtype;
  v_bal     integer;
  v_inviter_bal integer;
begin
  if v_uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  select email into v_email from auth.users where id = v_uid;

  select * into v_inv from public.invite_codes
   where upper(code) = upper(trim(p_code))
   for update;

  if not found then
    return jsonb_build_object('ok', false, 'reason', 'invalid');
  end if;
  if v_inv.revoked_at is not null then
    return jsonb_build_object('ok', false, 'reason', 'revoked');
  end if;
  if v_inv.expires_at is not null and v_inv.expires_at <= now() then
    return jsonb_build_object('ok', false, 'reason', 'expired');
  end if;
  if v_inv.used_count >= v_inv.max_uses then
    return jsonb_build_object('ok', false, 'reason', 'exhausted');
  end if;
  if v_inv.invited_email is not null and lower(v_inv.invited_email) <> lower(coalesce(v_email,'')) then
    return jsonb_build_object('ok', false, 'reason', 'email_mismatch');
  end if;
  if exists(select 1 from public.invite_redemptions where invite_code_id = v_inv.id and invitee_id = v_uid) then
    return jsonb_build_object('ok', false, 'reason', 'already_used');
  end if;
  -- 初回付与は1ユーザー1回のみ（別コードでの重複初回付与も防止）
  if exists(select 1 from public.token_ledger where user_id = v_uid and reason = 'invitee_initial_beta_grant') then
    -- 既に招待承認済みユーザー: beta_access のみ更新し、追加付与はしない
    update public.profiles set beta_access = true where id = v_uid;
    return jsonb_build_object('ok', true, 'granted', 0, 'note', 'already_granted');
  end if;

  -- 承認記録
  insert into public.invite_redemptions (invite_code_id, invitee_id, inviter_id, invitee_tokens, inviter_tokens)
  values (v_inv.id, v_uid, v_inv.invited_by, v_inv.token_grant_invitee, case when v_inv.invited_by is not null then v_inv.token_grant_inviter else 0 end);

  update public.invite_codes
     set used_count = used_count + 1,
         accepted_by = v_uid,
         accepted_at = now(),
         updated_at = now()
   where id = v_inv.id;

  -- invitee: beta_access + role + 初回トークン
  update public.profiles
     set beta_access = true,
         role = case when role = 'dentist' then v_inv.role else role end,
         tokens_remaining = tokens_remaining + v_inv.token_grant_invitee
   where id = v_uid
   returning tokens_remaining into v_bal;

  insert into public.token_ledger (user_id, delta, reason, balance_after, status, idempotency_key)
  values (v_uid, v_inv.token_grant_invitee, 'invitee_initial_beta_grant', v_bal, 'confirmed',
          'invitee:' || v_inv.id || ':' || v_uid);

  -- inviter: 紹介ボーナス（invited_by がある場合のみ・同一招待関係で1回）
  if v_inv.invited_by is not null and v_inv.token_grant_inviter > 0 then
    update public.profiles
       set tokens_remaining = tokens_remaining + v_inv.token_grant_inviter
     where id = v_inv.invited_by
     returning tokens_remaining into v_inviter_bal;
    if found then
      insert into public.token_ledger (user_id, delta, reason, balance_after, status, idempotency_key)
      values (v_inv.invited_by, v_inv.token_grant_inviter, 'inviter_referral_beta_bonus', v_inviter_bal, 'confirmed',
              'inviter:' || v_inv.id || ':' || v_uid)
      on conflict (idempotency_key) do nothing;
    end if;
  end if;

  return jsonb_build_object('ok', true, 'granted', v_inv.token_grant_invitee, 'balance', v_bal);
end;
$$;

revoke execute on function public.accept_invite_code(text) from public, anon;
grant  execute on function public.accept_invite_code(text) to authenticated;

-- ------------------------------------------------------------
-- 8) 管理者用 RPC（招待コード作成・無効化・手動トークン付与・フィードバック更新）
--    すべて is_admin() チェック + admin_audit_logs 記録付き
-- ------------------------------------------------------------
create or replace function public.admin_create_invite_code(
  p_code text default null,
  p_invited_email text default null,
  p_role text default 'dentist',
  p_workspace_type text default 'personal',
  p_token_grant_invitee integer default 100,
  p_token_grant_inviter integer default 100,
  p_max_uses integer default 1,
  p_expires_at timestamptz default null
) returns jsonb
language plpgsql security definer set search_path = public
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

create or replace function public.admin_revoke_invite_code(p_id uuid)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_uid uuid := auth.uid();
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  update public.invite_codes set revoked_at = now(), updated_at = now()
   where id = p_id and revoked_at is null;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_found_or_revoked'); end if;
  insert into public.admin_audit_logs (admin_user_id, action, target_type, target_id)
  values (v_uid, 'invite_code_revoked', 'invite_code', p_id::text);
  return jsonb_build_object('ok', true);
end;
$$;

create or replace function public.admin_grant_tokens(p_user_id uuid, p_amount integer, p_note text default null)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_uid uuid := auth.uid(); v_bal integer;
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  if p_amount = 0 then return jsonb_build_object('ok', false, 'reason', 'zero_amount'); end if;
  update public.profiles set tokens_remaining = tokens_remaining + p_amount
   where id = p_user_id returning tokens_remaining into v_bal;
  if not found then return jsonb_build_object('ok', false, 'reason', 'profile_not_found'); end if;
  insert into public.token_ledger (user_id, delta, reason, balance_after, status)
  values (p_user_id, p_amount, 'admin_grant', v_bal, 'confirmed');
  insert into public.admin_audit_logs (admin_user_id, action, target_type, target_id, metadata)
  values (v_uid, 'tokens_granted', 'user', p_user_id::text, jsonb_build_object('amount', p_amount, 'note', p_note));
  return jsonb_build_object('ok', true, 'balance', v_bal);
end;
$$;

create or replace function public.admin_update_feedback(p_id uuid, p_status text, p_admin_notes text default null)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_uid uuid := auth.uid();
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  update public.feedback_items
     set status = coalesce(p_status, status),
         admin_notes = coalesce(p_admin_notes, admin_notes),
         resolved_at = case when p_status = 'resolved' then now() else resolved_at end
   where id = p_id;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_found'); end if;
  insert into public.admin_audit_logs (admin_user_id, action, target_type, target_id, metadata)
  values (v_uid, 'feedback_updated', 'feedback_item', p_id::text, jsonb_build_object('status', p_status));
  return jsonb_build_object('ok', true);
end;
$$;

-- Feedback Inbox 閲覧の監査記録用（管理画面 open 時に1回呼ぶ）
create or replace function public.admin_log_feedback_view()
returns void
language plpgsql security definer set search_path = public
as $$
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  insert into public.admin_audit_logs (admin_user_id, action, target_type)
  values (auth.uid(), 'feedback_viewed', 'feedback_inbox');
end;
$$;

revoke execute on function public.admin_create_invite_code(text,text,text,text,integer,integer,integer,timestamptz) from public, anon;
revoke execute on function public.admin_revoke_invite_code(uuid) from public, anon;
revoke execute on function public.admin_grant_tokens(uuid,integer,text) from public, anon;
revoke execute on function public.admin_update_feedback(uuid,text,text) from public, anon;
revoke execute on function public.admin_log_feedback_view() from public, anon;
grant execute on function public.admin_create_invite_code(text,text,text,text,integer,integer,integer,timestamptz) to authenticated;
grant execute on function public.admin_revoke_invite_code(uuid) to authenticated;
grant execute on function public.admin_grant_tokens(uuid,integer,text) to authenticated;
grant execute on function public.admin_update_feedback(uuid,text,text) to authenticated;
grant execute on function public.admin_log_feedback_view() to authenticated;
-- （authenticated に grant するが、関数冒頭の is_admin() チェックで一般ユーザーは拒否される）
