-- ============================================================
-- migration 18: Library を Supabase を source of truth にする
--
-- 背景: Library は端末内 localStorage/IndexedDB のみに保存されていたため、
--   iOS の「ホーム画面に追加」standalone PWA は Safari と storage partition が
--   分かれ、保存済みプロジェクトが表示されない問題があった。
--   これを解決するため、ユーザーIDに紐づく Supabase 保存を正とする。
--
-- 本migrationで作成:
--   * public.library_projects テーブル（owner-only RLS・48h TTL）
--   * private storage bucket 'library-assets'（owner prefix RLS）
--   * cleanup_expired_library()（期限切れ行の削除。storageは best-effort でアプリ削除）
--
-- プライバシー: bucket は非公開（public=false）。参照は署名URL（有効期限付き）経由のみ。
--   患者画像（reference/after）を含むため、RLS で必ず本人のみアクセス可能に限定する。
-- ============================================================

create table if not exists public.library_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  client_id text not null,          -- 端末側レコードID（冪等・重複排除用）
  kind text,                        -- landmark-video / simulation-image / simulation / project
  title text,
  studio_type text,                 -- visual_simulation / morphing_video / project
  asset_type text,                  -- image / video / reference / project
  thumb_path text,                  -- storage path（サムネイル）
  asset_path text,                  -- storage path（本体: 生成画像 or 動画）
  reference_path text,              -- storage path（Reference/Before 画像。任意）
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '48 hours'),
  unique (user_id, client_id)
);

alter table public.library_projects enable row level security;
create index if not exists library_projects_user_exp_idx
  on public.library_projects(user_id, expires_at desc);

-- RLS: 本人のみ（select/insert/update/delete）。他人の display 画像・患者画像は不可視。
drop policy if exists "library own select" on public.library_projects;
create policy "library own select" on public.library_projects
  for select using ((select auth.uid()) = user_id);
drop policy if exists "library own insert" on public.library_projects;
create policy "library own insert" on public.library_projects
  for insert with check ((select auth.uid()) = user_id);
drop policy if exists "library own update" on public.library_projects;
create policy "library own update" on public.library_projects
  for update using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "library own delete" on public.library_projects;
create policy "library own delete" on public.library_projects
  for delete using ((select auth.uid()) = user_id);

-- private storage bucket
insert into storage.buckets (id, name, public)
values ('library-assets','library-assets', false)
on conflict (id) do nothing;

-- storage RLS: パスの先頭フォルダ = 本人 uid のもののみアクセス可（{uid}/{client_id}/...）
drop policy if exists "lib assets own read" on storage.objects;
create policy "lib assets own read" on storage.objects
  for select using (bucket_id='library-assets' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "lib assets own insert" on storage.objects;
create policy "lib assets own insert" on storage.objects
  for insert with check (bucket_id='library-assets' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "lib assets own update" on storage.objects;
create policy "lib assets own update" on storage.objects
  for update using (bucket_id='library-assets' and (storage.foldername(name))[1] = (select auth.uid())::text);
drop policy if exists "lib assets own delete" on storage.objects;
create policy "lib assets own delete" on storage.objects
  for delete using (bucket_id='library-assets' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- 期限切れ行の掃除（storage本体はアプリ側 best-effort 削除 + 読み取り時 expires_at フィルタ）
create or replace function public.cleanup_expired_library()
returns integer language plpgsql security definer set search_path to 'public' as $$
declare n integer;
begin
  delete from public.library_projects where expires_at < now();
  get diagnostics n = row_count;
  return n;
end;
$$;
revoke all on function public.cleanup_expired_library() from public, anon;
grant execute on function public.cleanup_expired_library() to authenticated;
