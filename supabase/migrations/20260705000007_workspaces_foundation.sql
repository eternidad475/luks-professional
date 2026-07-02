-- ============================================================
-- Phase 2.1a — migration 7 確定版: Workspace 基盤
-- workspaces / workspace_members / patients / cases / library_items /
-- workspace_invites + RLS helpers + personal workspace 自動作成 + バックフィル
--
-- 設計原則（レビュー確定 2026-07-02）:
--  * 臨床データ・トークンは user ではなく workspace 基準
--  * Library は「48時間一時保存スペース」— 長期クラウド保存は将来も行わない
--  * 患者の直接識別子（本名・電話・生年月日・カルテ番号）は保存しない
--  * Stripe参照は workspaces に持たせず billing_* 側に workspace_id を追加
--    （member への支払い情報露出を構造的に不可能にする）
--  * additive のみ・既存機能を壊さない・soft delete 基本
--  * トークン残高のコピーと消費RPCの切替は 2.1b（migration 8）で
--    同一トランザクション実施 — 2.1a 時点では profiles が引き続き「正」
-- ============================================================

-- ------------------------------------------------------------
-- 1) workspaces（Stripe列は持たない — billing_* が workspace_id を持つ）
-- ------------------------------------------------------------
create table if not exists public.workspaces (
  id               uuid primary key default gen_random_uuid(),
  type             text not null check (type in ('personal','clinic')),
  name             text not null,
  owner_user_id    uuid not null references auth.users(id),
  plan             text,
  tokens_remaining integer not null default 0,   -- 2.1b で「正」に昇格。それまで mirror
  clinic_phone     text,                          -- 医院代表電話（SMS認証とは無関係）
  clinic_address   text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  deleted_at       timestamptz                    -- 閉鎖 = soft delete
);
-- 1ユーザーにつき有効な personal workspace は1つ
create unique index if not exists workspaces_one_personal_idx
  on public.workspaces(owner_user_id) where (type='personal' and deleted_at is null);

-- ------------------------------------------------------------
-- 2) workspace_members
-- ------------------------------------------------------------
create table if not exists public.workspace_members (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  role         text not null default 'member' check (role in ('owner','admin','member')),
  status       text not null default 'active' check (status in ('active','invited','removed','left')),
  invited_by   uuid references auth.users(id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  removed_at   timestamptz,
  removed_by   uuid,
  unique (workspace_id, user_id)
);
create index if not exists workspace_members_user_idx on public.workspace_members(user_id, status);

-- §9-7: workspace owner は members に owner として存在（同一Tx内作成を許すため遅延制約）
create or replace function public.tg_ws_owner_membership() returns trigger
language plpgsql as $$
begin
  if not exists (
    select 1 from public.workspace_members m
     where m.workspace_id = new.id and m.user_id = new.owner_user_id
       and m.role = 'owner' and m.status = 'active'
  ) then
    raise exception 'workspace owner must be an active owner member (workspace %)', new.id;
  end if;
  return null;
end $$;
drop trigger if exists ws_owner_membership on public.workspaces;
create constraint trigger ws_owner_membership
  after insert on public.workspaces
  deferrable initially deferred
  for each row execute function public.tg_ws_owner_membership();

-- ------------------------------------------------------------
-- 3) RLS helpers（(select auth.uid()) / SECURITY DEFINER）
-- ------------------------------------------------------------
create or replace function public.ws_role(p_ws uuid) returns text
language sql stable security definer set search_path = public as $$
  select role from public.workspace_members
   where workspace_id = p_ws and user_id = (select auth.uid()) and status = 'active'
   limit 1;
$$;
create or replace function public.is_ws_member(p_ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.ws_role(p_ws) is not null;
$$;
create or replace function public.is_ws_admin(p_ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.ws_role(p_ws) in ('owner','admin');
$$;
create or replace function public.is_ws_owner(p_ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.ws_role(p_ws) = 'owner';
$$;
revoke execute on function public.ws_role(uuid), public.is_ws_member(uuid),
  public.is_ws_admin(uuid), public.is_ws_owner(uuid) from public, anon;
grant execute on function public.ws_role(uuid), public.is_ws_member(uuid),
  public.is_ws_admin(uuid), public.is_ws_owner(uuid) to authenticated;

-- ------------------------------------------------------------
-- 4) patients（匿名 patient_code。直接識別子カラムは設けない）
-- ------------------------------------------------------------
create table if not exists public.patients (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.workspaces(id) on delete cascade,
  patient_code  text not null,           -- §9-1: workspace内unique・匿名コード（例 P-0001）
  display_label text,                    -- 匿名ラベル（本名を入れない運用・UI側でも案内）
  sex           text,
  age           integer,
  memo          text,
  created_by    uuid not null references auth.users(id),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  deleted_at    timestamptz,
  unique (workspace_id, patient_code),
  unique (workspace_id, id)              -- 複合FK用（§9-2,4 の同一workspace保証）
);

-- ------------------------------------------------------------
-- 5) cases
-- ------------------------------------------------------------
create table if not exists public.cases (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id) on delete cascade,
  patient_id     uuid not null,
  case_title     text not null,
  treatment_type text,
  created_by     uuid not null references auth.users(id),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  deleted_at     timestamptz,
  unique (workspace_id, id),             -- 複合FK用（§9-3）
  unique (id, patient_id),               -- (case,patient) ペアFK用（§9-5）
  -- §9-2: case は同一 workspace の patient のみ
  foreign key (workspace_id, patient_id) references public.patients(workspace_id, id)
);
create index if not exists cases_patient_idx on public.cases(workspace_id, patient_id);

-- ------------------------------------------------------------
-- 6) library_items（48時間一時保存。長期保存プランは将来も作らない）
-- ------------------------------------------------------------
create table if not exists public.library_items (
  id             uuid primary key default gen_random_uuid(),
  workspace_id   uuid not null references public.workspaces(id) on delete cascade,
  patient_id     uuid,                   -- null = 「未整理」（後から紐付け可能）
  case_id        uuid,
  created_by     uuid not null references auth.users(id),
  item_type      text not null check (item_type in
    ('visual_simulation','morphing_video','uploaded_image','project','other')),
  title          text,
  storage_path   text,                   -- private bucket 内 {workspace_id}/{id}.*
  thumbnail_path text,
  metadata       jsonb,                  -- before/after参照・生成パラメータ・ledger_id等
  expires_at     timestamptz,            -- §9-11: ファイル系は必須（下のCHECK）
  files_deleted_at timestamptz,          -- 48h削除実行後にセット → UI「ファイル削除済み」
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  deleted_at     timestamptz,
  -- §9-4: patient は同一 workspace
  foreign key (workspace_id, patient_id) references public.patients(workspace_id, id),
  -- §9-3: case は同一 workspace
  foreign key (workspace_id, case_id)    references public.cases(workspace_id, id),
  -- §9-5: case と patient の両方がある場合、case.patient_id と矛盾しない
  --（複合FK: どちらかが null なら MATCH SIMPLE により制約はスキップされる）
  foreign key (case_id, patient_id)      references public.cases(id, patient_id),
  -- §9-11: ファイル系 item は expires_at 必須（48時間一時保存の強制）
  constraint library_items_expiry_required check (
    item_type not in ('visual_simulation','morphing_video','uploaded_image')
    or expires_at is not null
  )
);
create index if not exists library_items_ws_idx on public.library_items(workspace_id, created_at desc);
create index if not exists library_items_patient_idx on public.library_items(workspace_id, patient_id, created_at desc);
create index if not exists library_items_expiry_idx on public.library_items(expires_at)
  where files_deleted_at is null and expires_at is not null;

-- §9-6: created_by は作成時点で active な workspace member（patients/cases/library_items 共通）
create or replace function public.tg_check_creator_membership() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if not exists (
    select 1 from public.workspace_members m
     where m.workspace_id = new.workspace_id and m.user_id = new.created_by
       and m.status = 'active'
  ) then
    raise exception 'created_by % is not an active member of workspace %', new.created_by, new.workspace_id;
  end if;
  return new;
end $$;
drop trigger if exists patients_creator_member on public.patients;
create trigger patients_creator_member before insert on public.patients
  for each row execute function public.tg_check_creator_membership();
drop trigger if exists cases_creator_member on public.cases;
create trigger cases_creator_member before insert on public.cases
  for each row execute function public.tg_check_creator_membership();
drop trigger if exists library_creator_member on public.library_items;
create trigger library_creator_member before insert on public.library_items
  for each row execute function public.tg_check_creator_membership();

-- ------------------------------------------------------------
-- 7) workspace_invites（Clinicメンバー招待。ベータ入場用 invite_codes とは別）
-- ------------------------------------------------------------
create table if not exists public.workspace_invites (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references public.workspaces(id) on delete cascade,
  code          text not null unique,
  invited_email text,
  role          text not null default 'member' check (role in ('admin','member')),
  invited_by    uuid not null references auth.users(id),
  max_uses      integer not null default 1,
  used_count    integer not null default 0,
  expires_at    timestamptz,
  revoked_at    timestamptz,
  created_at    timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 8) 既存テーブルの additive 拡張
-- ------------------------------------------------------------
-- §9-9,10: ledger の紐付けキー（workspace_id/case_id は migration 1 で追加済み）
alter table public.token_ledger add column if not exists patient_id uuid;
-- 新規消費経路（2.1b RPC）では workspace_id を必須化。既存行バックフィル後、
-- NOT NULL 制約は旧RPC完全廃止後（2.1c）に適用する。
-- billing の workspace 帰属（§3: 既存契約は personal workspace へ）
alter table public.billing_customers     add column if not exists workspace_id uuid references public.workspaces(id);
alter table public.billing_subscriptions add column if not exists workspace_id uuid references public.workspaces(id);

-- ------------------------------------------------------------
-- 9) RLS
-- ------------------------------------------------------------
alter table public.workspaces        enable row level security;
alter table public.workspace_members enable row level security;
alter table public.patients          enable row level security;
alter table public.cases             enable row level security;
alter table public.library_items     enable row level security;
alter table public.workspace_invites enable row level security;

-- workspaces: member なら閲覧可（Stripe列は存在しないため露出リスクなし）。
-- 更新（Clinic情報編集）は owner のみ。削除ポリシーなし（閉鎖はRPC/soft delete）。
drop policy if exists "ws member read"   on public.workspaces;
drop policy if exists "ws owner update"  on public.workspaces;
create policy "ws member read"  on public.workspaces
  for select using (public.is_ws_member(id) and deleted_at is null);
create policy "ws owner update" on public.workspaces
  for update using (public.is_ws_owner(id)) with check (public.is_ws_owner(id));

-- workspace_members: メンバー同士は一覧可（他人の profiles は own-row RLS のため
-- display_name 等の個人詳細には到達不可 = 代表者個人情報の遮蔽は構造的に担保）
drop policy if exists "ws members read" on public.workspace_members;
create policy "ws members read" on public.workspace_members
  for select using (public.is_ws_member(workspace_id));
-- insert/update は RPC（2.1c）と service_role のみ（policyなし）

-- patients / cases / library_items: member read+insert、update は member、
-- soft delete（deleted_at 更新を含む update）も member。物理 delete 不可。
drop policy if exists "patients member read"   on public.patients;
drop policy if exists "patients member insert" on public.patients;
drop policy if exists "patients member update" on public.patients;
create policy "patients member read"   on public.patients
  for select using (public.is_ws_member(workspace_id));
create policy "patients member insert" on public.patients
  for insert with check (public.is_ws_member(workspace_id) and created_by = (select auth.uid()));
create policy "patients member update" on public.patients
  for update using (public.is_ws_member(workspace_id)) with check (public.is_ws_member(workspace_id));

drop policy if exists "cases member read"   on public.cases;
drop policy if exists "cases member insert" on public.cases;
drop policy if exists "cases member update" on public.cases;
create policy "cases member read"   on public.cases
  for select using (public.is_ws_member(workspace_id));
create policy "cases member insert" on public.cases
  for insert with check (public.is_ws_member(workspace_id) and created_by = (select auth.uid()));
create policy "cases member update" on public.cases
  for update using (public.is_ws_member(workspace_id)) with check (public.is_ws_member(workspace_id));

drop policy if exists "library member read"   on public.library_items;
drop policy if exists "library member insert" on public.library_items;
drop policy if exists "library member update" on public.library_items;
create policy "library member read"   on public.library_items
  for select using (public.is_ws_member(workspace_id));
create policy "library member insert" on public.library_items
  for insert with check (public.is_ws_member(workspace_id) and created_by = (select auth.uid()));
create policy "library member update" on public.library_items
  for update using (public.is_ws_member(workspace_id)) with check (public.is_ws_member(workspace_id));

-- workspace_invites: owner/admin のみ
drop policy if exists "ws invites admin read" on public.workspace_invites;
create policy "ws invites admin read" on public.workspace_invites
  for select using (public.is_ws_admin(workspace_id));

-- billing_*: workspace owner にも read を追加（memberは不可のまま）
drop policy if exists "ws owner customer read" on public.billing_customers;
create policy "ws owner customer read" on public.billing_customers
  for select using (workspace_id is not null and public.is_ws_owner(workspace_id));
drop policy if exists "ws owner subscription read" on public.billing_subscriptions;
create policy "ws owner subscription read" on public.billing_subscriptions
  for select using (workspace_id is not null and public.is_ws_owner(workspace_id));

-- token_ledger: Clinic owner/admin はメンバー別消費を確認可能（生成内容は含まれない）
drop policy if exists "ws admin ledger read" on public.token_ledger;
create policy "ws admin ledger read" on public.token_ledger
  for select using (workspace_id is not null and public.is_ws_admin(workspace_id));

-- ------------------------------------------------------------
-- 10) personal workspace 自動作成（新規ユーザー）
-- ------------------------------------------------------------
create or replace function public.create_personal_workspace(p_user uuid, p_name text)
returns uuid
language plpgsql security definer set search_path = public as $$
declare v_ws uuid;
begin
  select id into v_ws from public.workspaces
   where owner_user_id = p_user and type = 'personal' and deleted_at is null;
  if v_ws is not null then return v_ws; end if;
  insert into public.workspaces (type, name, owner_user_id, tokens_remaining)
  values ('personal', coalesce(nullif(trim(p_name),''),'Personal'), p_user, 0)
  returning id into v_ws;
  insert into public.workspace_members (workspace_id, user_id, role, status)
  values (v_ws, p_user, 'owner', 'active')
  on conflict (workspace_id, user_id) do nothing;
  return v_ws;
end $$;
revoke execute on function public.create_personal_workspace(uuid, text) from public, anon, authenticated;

-- handle_new_user v3: profiles + 0付与ledger + personal workspace
create or replace function public.handle_new_user()
returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, tokens_remaining)
  values (new.id, 0)
  on conflict (id) do nothing;
  insert into public.token_ledger (user_id, delta, reason, balance_after, status)
  values (new.id, 0, 'signup_initial_grant', 0, 'confirmed');
  perform public.create_personal_workspace(new.id, split_part(coalesce(new.email,''),'@',1));
  return new;
end $$;
revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- ------------------------------------------------------------
-- 11) バックフィル（既存ユーザー・既存契約・既存ledger）
--     残高コピーはここでは行わない（2.1b で RPC 切替と同時に実施）
-- ------------------------------------------------------------
do $$
declare r record; v_ws uuid;
begin
  for r in
    select p.id as user_id,
           coalesce(nullif(p.display_name,''), split_part(coalesce(u.email,''),'@',1), 'Personal') as nm
      from public.profiles p
      join auth.users u on u.id = p.id
     where not exists (
       select 1 from public.workspaces w
        where w.owner_user_id = p.id and w.type = 'personal' and w.deleted_at is null)
  loop
    v_ws := public.create_personal_workspace(r.user_id, r.nm);
  end loop;

  -- §3: 既存 Stripe 契約を personal workspace に帰属
  update public.billing_customers bc
     set workspace_id = w.id
    from public.workspaces w
   where bc.workspace_id is null
     and w.owner_user_id = bc.user_id and w.type = 'personal' and w.deleted_at is null;
  update public.billing_subscriptions bs
     set workspace_id = w.id
    from public.workspaces w
   where bs.workspace_id is null
     and w.owner_user_id = bs.user_id and w.type = 'personal' and w.deleted_at is null;

  -- §1: 既存 ledger を personal workspace に backfill（可能な範囲）
  update public.token_ledger tl
     set workspace_id = w.id
    from public.workspaces w
   where tl.workspace_id is null
     and w.owner_user_id = tl.user_id and w.type = 'personal' and w.deleted_at is null;
end $$;

-- ============================================================
-- 適用後の確認（手動）:
--  select count(*) from workspaces where type='personal';       -- = profiles数
--  select count(*) from token_ledger where workspace_id is null; -- = 0 が理想
--  select count(*) from billing_customers where workspace_id is null; -- = 0
-- ============================================================
