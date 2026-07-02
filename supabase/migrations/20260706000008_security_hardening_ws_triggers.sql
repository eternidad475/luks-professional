-- ============================================================
-- Phase 2.1a 追補 — migration 8: security hardening only
-- Supabase security advisor WARN 2件の解消に限定。
-- 機能変更・ロジック変更・スキーマ変更・RLS変更は一切含まない。
--
-- 対象WARN:
--  1) function_search_path_mutable:
--     public.tg_ws_owner_membership の search_path が未固定
--  2) anon/authenticated_security_definer_function_executable:
--     public.tg_check_creator_membership（trigger専用・SECURITY DEFINER）が
--     /rest/v1/rpc/ 経由で anon / authenticated から直接実行可能
--
-- 方針:
--  * function body は migration 7 と完全に同一（ロジック不変）
--  * search_path は public, pg_temp に固定
--  * trigger専用関数は PUBLIC / anon / authenticated から EXECUTE を revoke
--    （trigger の発火は実行時に呼び出し元の EXECUTE 権限を要求しないため、
--      workspaces / patients / cases / library_items への insert 動作には影響しない）
--  * どの role にも再 grant しない（関数所有者=postgres のみ実行可能。
--    trigger 経由の実行はこれで十分）
-- ============================================================

-- ------------------------------------------------------------
-- 1) tg_ws_owner_membership: search_path 固定（body は migration 7 と同一）
-- ------------------------------------------------------------
create or replace function public.tg_ws_owner_membership() returns trigger
language plpgsql set search_path = public, pg_temp as $$
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

-- ------------------------------------------------------------
-- 2) tg_check_creator_membership: search_path を pg_temp 含みで固定
--    （SECURITY DEFINER・body は migration 7 と同一）
-- ------------------------------------------------------------
create or replace function public.tg_check_creator_membership() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
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

-- ------------------------------------------------------------
-- 3) trigger専用関数の直接RPC実行を遮断
--    （returns trigger のため通常は呼べないが、PostgREST スキーマ上の
--      露出と advisor WARN を消すため明示的に revoke）
-- ------------------------------------------------------------
revoke execute on function public.tg_ws_owner_membership()      from public;
revoke execute on function public.tg_ws_owner_membership()      from anon;
revoke execute on function public.tg_ws_owner_membership()      from authenticated;
revoke execute on function public.tg_check_creator_membership() from public;
revoke execute on function public.tg_check_creator_membership() from anon;
revoke execute on function public.tg_check_creator_membership() from authenticated;

-- ============================================================
-- 適用後の確認（手動）:
--  * Supabase security advisor 再実行 → 上記2 WARN が消えていること
--  * select count(*) from workspaces where type='personal';        -- = profiles数
--  * select count(*) from token_ledger where workspace_id is null;  -- = 0
--  * select count(*) from billing_customers where workspace_id is null; -- = 0
--  * workspace_members: 既存ユーザーの owner membership が active のまま
--  * 動作確認: 新規ユーザー作成（personal workspace 自動作成）が成功すること
-- ============================================================
