-- ============================================================
-- Hotfix — migration 11: 新規サインアップが 500 で失敗する不具合の修正
--
-- 症状: POST /auth/v1/signup が
--   "database error on committing or rolling back transaction:
--    ERROR: permission denied for table workspace_members (SQLSTATE 42501)"
--
-- 根本原因:
--   migration 7 の遅延制約トリガー ws_owner_membership の関数
--   tg_ws_owner_membership が SECURITY INVOKER のままだった。
--   サインアップは GoTrue の DB ロール supabase_auth_admin で走り、
--   COMMIT 時に発火する deferred constraint trigger は呼び出し元ロール権限で
--   実行される → supabase_auth_admin は public.workspace_members への
--   SELECT 権限を持たないため 42501 で COMMIT ごと失敗する。
--   （migration 7 適用後、新規サインアップは全て失敗する状態だった。
--     既存2ユーザーは migration 7 適用前の登録のため顕在化せず）
--
-- 修正: SECURITY DEFINER + search_path 固定に変更（body は不変）。
--   同種の tg_check_creator_membership は当初から SECURITY DEFINER であり
--   これと整合する。migration 8 の revoke（public/anon/authenticated から
--   EXECUTE 剥奪）は維持する。
-- ============================================================

create or replace function public.tg_ws_owner_membership() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
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

-- SECURITY DEFINER 化に伴い、直接RPC実行の遮断を再徹底（migration 8 と同じ方針）
revoke execute on function public.tg_ws_owner_membership() from public;
revoke execute on function public.tg_ws_owner_membership() from anon;
revoke execute on function public.tg_ws_owner_membership() from authenticated;

-- ============================================================
-- 適用後の確認（手動）:
--  * POST /auth/v1/signup が 200 を返し、profiles / personal workspace /
--    owner membership が作成されること
--  * 確認メールが custom SMTP（no-reply@auth.caseflow-studio.com）から届くこと
-- ============================================================
