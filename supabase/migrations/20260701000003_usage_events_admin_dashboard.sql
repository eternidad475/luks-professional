-- ============================================================
-- Phase 1 Emergency Beta Gate — migration 3/3
-- usage_events + Admin Dashboard 用 RPC / 追加列 / 追加policy
-- 追加（additive）のみ。既存オブジェクトの破壊的変更なし。冪等。
-- 前提: 20260701000001 / 20260701000002 適用済み（is_admin() を使用）
-- ============================================================

-- ------------------------------------------------------------
-- 1) profiles: 表示名・職種確認などの任意プロフィール列（全て additive）
--    ※ 本名・住所・電話番号・生年月日・免許番号は保存しない方針
-- ------------------------------------------------------------
alter table public.profiles
  add column if not exists display_name           text,
  add column if not exists professional_type      text,
  add column if not exists prefecture             text,
  add column if not exists professional_confirmed boolean not null default false,
  add column if not exists professional_verified  boolean not null default false,
  add column if not exists account_status         text not null default 'active';

do $$ begin
  alter table public.profiles
    add constraint profiles_account_status_check check (account_status in ('active','suspended','deleted'));
exception when duplicate_object then null; end $$;

-- ------------------------------------------------------------
-- 2) usage_events（使用状況イベント台帳）
--    患者名・カルテ番号等の直接識別情報は記録しない。
--    metadata に個人情報・画像データを入れないこと（運用ルール）。
-- ------------------------------------------------------------
create table if not exists public.usage_events (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid references auth.users(id) on delete set null,
  organization_id uuid,
  workspace_id    uuid,
  case_id         uuid,
  event_type      text not null,   -- user_signed_in / invite_code_accepted / visual_simulation_generated / morphing_video_exported / token_consumed / token_granted / feedback_submitted / generation_failed / export_failed / library_save_failed / token_empty / ...
  feature         text,            -- visual-simulation / morphing-video / photo-manager / library / export / auth / token / feedback
  action          text,
  metadata        jsonb,
  page_path       text,
  user_agent      text,
  environment     text,            -- production / preview / staging / local
  created_at      timestamptz not null default now()
);
create index if not exists usage_events_type_idx on public.usage_events(event_type, created_at desc);
create index if not exists usage_events_user_idx on public.usage_events(user_id, created_at desc);

alter table public.usage_events enable row level security;

drop policy if exists "user insert own events" on public.usage_events;
drop policy if exists "admin read events"      on public.usage_events;
-- 一般ユーザー: 自分の user_id での insert のみ（select 不可）
create policy "user insert own events" on public.usage_events
  for insert with check ((select auth.uid()) = user_id);
create policy "admin read events" on public.usage_events
  for select using (public.is_admin());

-- ------------------------------------------------------------
-- 3) 管理者向け追加 read policy（additive: 既存の own-row policy はそのまま）
-- ------------------------------------------------------------
drop policy if exists "admin read profiles" on public.profiles;
create policy "admin read profiles" on public.profiles
  for select using (public.is_admin());

drop policy if exists "admin read ledger" on public.token_ledger;
create policy "admin read ledger" on public.token_ledger
  for select using (public.is_admin());

-- ------------------------------------------------------------
-- 4) admin_overview(): ダッシュボード Overview 用の集計（admin専用）
-- ------------------------------------------------------------
create or replace function public.admin_overview()
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v jsonb;
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  select jsonb_build_object(
    'total_users',        (select count(*) from public.profiles),
    'invited_users',      (select count(*) from public.profiles where beta_access),
    'active_users_7d',    (select count(distinct user_id) from public.usage_events where created_at > now() - interval '7 days'),
    'active_invite_codes',(select count(*) from public.invite_codes
                            where revoked_at is null and used_count < max_uses
                              and (expires_at is null or expires_at > now())),
    'pending_feedback',   (select count(*) from public.feedback_items where status = 'new'),
    'tokens_consumed_today',(select coalesce(-sum(delta),0) from public.token_ledger
                              where delta < 0 and created_at >= date_trunc('day', now())),
    'tokens_granted_today',(select coalesce(sum(delta),0) from public.token_ledger
                              where delta > 0 and created_at >= date_trunc('day', now())),
    'generations_today',  (select count(*) from public.token_ledger
                              where delta < 0 and created_at >= date_trunc('day', now())),
    'errors_today',       (select count(*) from public.usage_events
                              where event_type like '%\_failed' escape '\'
                                and created_at >= date_trunc('day', now())),
    'events_today',       (select count(*) from public.usage_events
                              where created_at >= date_trunc('day', now()))
  ) into v;
  return v;
end;
$$;

-- ------------------------------------------------------------
-- 5) admin_list_users(): ユーザー一覧（email / last_sign_in は auth.users から）
-- ------------------------------------------------------------
create or replace function public.admin_list_users()
returns table(
  id uuid, email text, display_name text, role text, beta_access boolean,
  professional_confirmed boolean, professional_verified boolean, account_status text,
  tokens_remaining integer, clinic_name text, created_at timestamptz, last_sign_in_at timestamptz
)
language plpgsql security definer set search_path = public
as $$
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  return query
    select p.id, u.email::text, p.display_name, p.role, p.beta_access,
           p.professional_confirmed, p.professional_verified, p.account_status,
           p.tokens_remaining, p.clinic_name, p.created_at, u.last_sign_in_at
      from public.profiles p
      join auth.users u on u.id = p.id
     order by p.created_at desc
     limit 200;
end;
$$;

-- ------------------------------------------------------------
-- 6) admin_set_user_role(): role変更（監査ログ付き）
-- ------------------------------------------------------------
create or replace function public.admin_set_user_role(p_user_id uuid, p_role text)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare v_uid uuid := auth.uid(); v_old text;
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  if p_role not in ('developer','co_developer','owner','admin','dentist','staff','viewer','billing_manager','patient_link_viewer') then
    return jsonb_build_object('ok', false, 'reason', 'invalid_role');
  end if;
  select role into v_old from public.profiles where id = p_user_id;
  if not found then return jsonb_build_object('ok', false, 'reason', 'not_found'); end if;
  update public.profiles set role = p_role where id = p_user_id;
  insert into public.admin_audit_logs (admin_user_id, action, target_type, target_id, metadata)
  values (v_uid, 'user_role_changed', 'user', p_user_id::text,
          jsonb_build_object('old_role', v_old, 'new_role', p_role));
  return jsonb_build_object('ok', true);
end;
$$;

-- ------------------------------------------------------------
-- 7) 実行権限
-- ------------------------------------------------------------
revoke execute on function public.admin_overview()                     from public, anon;
revoke execute on function public.admin_list_users()                   from public, anon;
revoke execute on function public.admin_set_user_role(uuid, text)      from public, anon;
grant  execute on function public.admin_overview()                     to authenticated;
grant  execute on function public.admin_list_users()                   to authenticated;
grant  execute on function public.admin_set_user_role(uuid, text)      to authenticated;
-- （authenticated に grant するが、各関数冒頭の is_admin() で一般ユーザーは拒否）
