-- ============================================================
-- Phase 1 Emergency Beta Gate — migration 2/2 (security hardening)
-- 提案段階。既存 policy / handle_new_user() に触れるため、
-- リスクは docs/phase1-emergency-beta-gate.md §3.2 を参照のこと。
-- 全体を1トランザクションとして適用する（Postgres DDL はトランザクショナル）。
-- ============================================================

-- ------------------------------------------------------------
-- 1) 既存 RLS policy: auth.uid() → (select auth.uid()) 化（initplan 最適化）
--    + profiles update に WITH CHECK 追加
--    ※ drop→create は同一トランザクション内なので瞬断なし
-- ------------------------------------------------------------
drop policy if exists "own profile read"      on public.profiles;
create policy "own profile read" on public.profiles
  for select using ((select auth.uid()) = id);

drop policy if exists "own profile update"    on public.profiles;
create policy "own profile update" on public.profiles
  for update using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

drop policy if exists "own subscription read" on public.subscriptions;
create policy "own subscription read" on public.subscriptions
  for select using ((select auth.uid()) = user_id);

drop policy if exists "own ledger read" on public.token_ledger;
create policy "own ledger read" on public.token_ledger
  for select using ((select auth.uid()) = user_id);

-- ------------------------------------------------------------
-- 2) handle_new_user(): 招待制ベータ移行に伴い、サインアップ時の
--    自動10トークン付与を 0 に変更（初回付与は招待承認時の100に一本化）。
--    【リスク】招待コードなしで登録したユーザーはトークン0。
--    これは招待制の仕様どおり（未招待ユーザーはアプリ本体を利用不可）。
--    既存ユーザーの残高には影響しない。
--    【ロールバック】旧定義は supabase/schema.sql §Phase 3-B-1 を参照。
-- ------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, tokens_remaining)
  values (new.id, 0)
  on conflict (id) do nothing;

  insert into public.token_ledger (user_id, delta, reason, balance_after, status)
  values (new.id, 0, 'signup_initial_grant', 0, 'confirmed');

  return new;
end;
$$;

revoke execute on function public.handle_new_user() from public, anon, authenticated;

-- ------------------------------------------------------------
-- 3) consume_token(): reason の記録形式は既存のまま。
--    SECURITY DEFINER + authenticated 実行可は仕様（本人の残高のみ操作）。
--    Advisor 警告 0029 は「意図された設計」としてここに明記する。
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 4) 【手動・ダッシュボード操作が必要（SQL では設定不可）】
--    Authentication → Sign In / Providers → Password →
--    "Leaked password protection" を有効化すること。
-- ------------------------------------------------------------
