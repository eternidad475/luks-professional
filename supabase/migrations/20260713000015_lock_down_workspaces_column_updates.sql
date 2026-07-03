-- ============================================================
-- migration 15: workspaces の列レベル UPDATE/INSERT 権限を最小化
-- 本番適用済み: 2026-07-13（schema_migrations version は docs 参照）
--
-- 背景（潜在的な権限/経済的昇格）:
--   RLS "ws owner update"（is_ws_owner）により workspace owner は自分の
--   workspace 行を UPDATE できるが、列 GRANT が type/plan/tokens_remaining/
--   owner_user_id/deleted_at を含む全列に付与されていた。このため owner が
--   clinic wallet（workspaces.tokens_remaining）を自己増加、type を clinic に
--   自己変更、plan を自己変更、論理削除 deleted_at を操作できてしまう。
--   profiles と同型の「緩いRLS × 広い列GRANT」問題（profiles は migration 12
--   で修正済み）。
--
-- 修正:
--   workspaces の UPDATE を authenticated/anon から剥奪し、owner が安全に
--   編集してよい表示情報（name / clinic_phone / clinic_address）のみ再付与。
--   type / plan / tokens_remaining / owner_user_id / deleted_at / id /
--   created_at は列 GRANT を持たないため直接 UPDATE 不可となり、変更は
--   SECURITY DEFINER RPC（accept_invite_code, create_personal_workspace,
--   handle_new_user 等）または将来の owner-gated 移行 RPC / 管理者処理のみに限定。
--   INSERT は anon/authenticated から剥奪（workspaces はサインアップトリガー
--   = SECURITY DEFINER で作成されるため影響なし）。
-- ============================================================

revoke update on public.workspaces from authenticated;
revoke update on public.workspaces from anon;
revoke insert on public.workspaces from authenticated;
revoke insert on public.workspaces from anon;

grant update (name, clinic_phone, clinic_address) on public.workspaces to authenticated;

-- ============================================================
-- 適用後の確認（本番で実測済み・2026-07-13）:
--  * owner が workspaces.tokens_remaining / type / plan / deleted_at を UPDATE
--    → いずれも DENIED (42501)
--  * owner が name を UPDATE → OK（RLS: is_ws_owner, 列GRANTあり）
--  * removed/left member は ws_role()（status='active' フィルタ）により
--    is_ws_member/is_ws_owner が false となり cases/patients/library_items/
--    billing すべてアクセス不可（RLS 層で自動失効）— 別途確認済み
-- ============================================================
