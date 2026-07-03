-- ============================================================
-- Security fix — migration 12: profiles の列レベル UPDATE 権限を最小化
--
-- 症状（脆弱性）:
--   一般ユーザー（authenticated ロール）が REST 経由で自分の profiles 行を
--   PATCH し、role='admin' への昇格や tokens_remaining の自己水増しが可能だった。
--   本番DBで再現確認済み（role='admin', tokens_remaining=999999 の書き込みが
--   rows=1 で成功。テストユーザーは即時復元）。
--
-- 根本原因:
--   ・RLS ポリシー "own profile update" が USING/WITH CHECK = (auth.uid() = id)
--     で自分の行の UPDATE を許可（これ自体は正当）。
--   ・一方で profiles の UPDATE 権限が列を限定せず authenticated / anon に
--     付与されていたため、RLS を通過した自分の行に対して role・
--     tokens_remaining・beta_access 等の特権列まで書き換えできた。
--   ・RLS は「どの行か」しか制限できず「どの列か」は列レベル GRANT で制御する
--     必要がある。列 GRANT が広すぎたことが原因。
--   ・profiles に UPDATE を許可する管理者向けポリシーは存在せず、role 変更等は
--     SECURITY DEFINER RPC（admin_set_user_role / admin_grant_tokens /
--     consume_token(s) / サインアップトリガー）経由のみが正規経路。
--
-- 修正方針:
--   テーブル全体の UPDATE 権限を authenticated / anon から剥奪し、アプリが
--   セルフサービスで正当に更新する列だけを再付与する。
--   再付与する列（クライアントの profiles.update ペイロードと一致）:
--     display_name / clinic_name / professional_type / professional_confirmed
--   これ以外（role, tokens_remaining, beta_access, account_status,
--     professional_verified, stripe_customer_id, trial_tokens_granted,
--     id, created_at 等）は列 GRANT を持たないため直接 UPDATE 不可となり、
--     変更は SECURITY DEFINER RPC / 管理者経路のみに限定される。
--
--   professional_confirmed はサインアップ時の本人申告チェック（self-attestation）
--   のため残す。professional_verified（管理者による確認フラグ）は付与しない。
--
--   anon の INSERT/UPDATE 列 GRANT も併せて剥奪（profiles には anon 向けの
--   INSERT/UPDATE ポリシーが無く RLS で既に遮断されるが、多層防御として権限も
--   落とす。新規サインアップ時の profiles 生成は SECURITY DEFINER の
--   handle_new_user トリガー = postgres 権限で走るため影響なし）。
-- ============================================================

revoke update on public.profiles from authenticated;
revoke update on public.profiles from anon;
revoke insert on public.profiles from anon;

-- セルフサービスで更新してよい列のみ再付与（プロフィール編集シート＋
-- サインアップ時の職種の本人申告）
grant update (display_name, clinic_name, professional_type, professional_confirmed)
  on public.profiles to authenticated;

-- ============================================================
-- 適用後の確認（本番で実測済み・2026-07-10）:
--  * authenticated ロールで自分の行に role='admin', tokens_remaining=999999 を
--    UPDATE → permission denied (SQLSTATE 42501) で BLOCKED
--  * authenticated ロールで自分の行に display_name を UPDATE → OK（rows=1）
--  * admin_* RPC（create_invite_code / grant_tokens / set_user_role /
--    list_users）を非管理者で実行 → いずれも 42501 で DENIED（各RPCが内部で
--    is_admin() を検証しているため設計通り）
--  * invite_codes への直接 INSERT を非管理者で実行 → 42501 で DENIED
-- ============================================================
