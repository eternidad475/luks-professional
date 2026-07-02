-- ============================================================
-- Phase 1d — migration 4: admin_list_users v2（電話番号・職種・電話認証状態）
-- 提案段階（Supabase MCP 再接続後に適用）。
-- 戻り値の型が変わるため drop→create（関数のみ・データ破壊なし）。
-- 電話番号は auth.users.phone / phone_confirmed_at を参照（E.164）。
-- 管理画面では初期表示マスク・必要時のみ全文表示（フロント側で制御）。
-- ============================================================

drop function if exists public.admin_list_users();

create or replace function public.admin_list_users()
returns table(
  id uuid, email text, display_name text, role text, beta_access boolean,
  professional_confirmed boolean, professional_verified boolean, professional_type text,
  account_status text, tokens_remaining integer, clinic_name text,
  phone text, phone_verified boolean,
  created_at timestamptz, last_sign_in_at timestamptz
)
language plpgsql security definer set search_path = public
as $$
begin
  if not public.is_admin() then
    raise exception 'admin only' using errcode = '42501';
  end if;
  return query
    select p.id, u.email::text, p.display_name, p.role, p.beta_access,
           p.professional_confirmed, p.professional_verified, p.professional_type,
           p.account_status, p.tokens_remaining, p.clinic_name,
           u.phone::text, (u.phone_confirmed_at is not null) as phone_verified,
           p.created_at, u.last_sign_in_at
      from public.profiles p
      join auth.users u on u.id = p.id
     order by p.created_at desc
     limit 200;
end;
$$;

revoke execute on function public.admin_list_users() from public, anon;
grant  execute on function public.admin_list_users() to authenticated;
-- （関数冒頭の is_admin() チェックで一般ユーザーは拒否）

-- ------------------------------------------------------------
-- 【手動・ダッシュボード操作（SQL不可）】SMS OTP を有効化する場合:
-- Authentication → Sign In / Providers → Phone を有効化し、
-- SMSプロバイダ（Twilio 等）の資格情報をダッシュボードに設定する。
-- 注意: SMSコストと SIMスワップリスクがあるため、電話認証は
-- 「本人確認の補助」として扱い、単独の資格情報として過信しない。
-- ============================================================
