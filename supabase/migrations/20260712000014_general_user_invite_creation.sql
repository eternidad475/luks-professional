-- ============================================================
-- migration 14: 一般ユーザーによる新規ユーザー招待コード発行
-- 本番適用済み: supabase_migrations version = (下記 docs 参照), 2026-07-12
--
-- 目的: 一般ユーザー（onboarded / beta_access=true）も Invite ページから
--   「新規ユーザー招待コード」を発行できるようにする。ただし:
--     * 発行できる role は dentist のみ（フロント指定を一切受け付けない）
--     * 招待者ボーナスなし（token_grant_inviter を 0 に固定）
--     * 新規ユーザーには redeem 時に 10 トークン付与（token_grant_invitee=10）
--     * 同時に有効な未使用コードは最大 5 件まで
--     * invited_by = auth.uid() を必ず記録（発行者本人）
--   一般ユーザーは invite_codes を直接 INSERT できない（RLS は admin のみ許可）。
--   発行は必ずこの SECURITY DEFINER RPC 経由。role/bonus はDB側で固定するため
--   フロント改ざん・RPC直叩きでも dentist 以外/ボーナス付与は不可能。
--
--   招待者ボーナス（inviter +5）は本 RPC 経由の発行では一切発生しない。
--   （accept_invite_code は token_grant_inviter>0 のときのみ inviter へ加算するが、
--     本 RPC は 0 固定なので加算経路に入らない。既存の admin 発行コードは従来通り。）
-- ============================================================

create or replace function public.create_user_invite()
 returns jsonb
 language plpgsql
 security definer
 set search_path to 'public', 'pg_temp'
as $function$
declare
  v_uid uuid := auth.uid();
  v_confirmed timestamptz;
  v_beta boolean;
  v_active int;
  v_code text;
  v_id uuid;
begin
  if v_uid is null then
    return jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  end if;

  select email_confirmed_at into v_confirmed from auth.users where id = v_uid;
  if v_confirmed is null then
    return jsonb_build_object('ok', false, 'reason', 'email_unconfirmed');
  end if;

  select beta_access into v_beta from public.profiles where id = v_uid;
  if not coalesce(v_beta, false) then
    return jsonb_build_object('ok', false, 'reason', 'not_activated');
  end if;

  -- 同時に有効な未使用コードは最大5件（使用済み/失効/revoke済みは数えない）
  select count(*) into v_active from public.invite_codes
   where invited_by = v_uid
     and revoked_at is null
     and used_count < max_uses
     and (expires_at is null or expires_at > now());
  if v_active >= 5 then
    return jsonb_build_object('ok', false, 'reason', 'limit_reached', 'active', v_active);
  end if;

  v_code := 'CF-' || upper(substr(replace(gen_random_uuid()::text,'-',''),1,8));

  -- role=dentist / inviter bonus=0 / invitee grant=10 をDB側で固定
  insert into public.invite_codes
    (code, invited_email, invited_by, workspace_type, role,
     token_grant_invitee, token_grant_inviter, max_uses, expires_at)
  values
    (v_code, null, v_uid, 'personal', 'dentist', 10, 0, 1, null)
  returning id into v_id;

  return jsonb_build_object('ok', true, 'id', v_id, 'code', v_code, 'active', v_active + 1);
end;
$function$;

revoke execute on function public.create_user_invite() from public;
revoke execute on function public.create_user_invite() from anon;
grant execute on function public.create_user_invite() to authenticated;

-- 一般ユーザーが自分の発行したコード履歴を SELECT できるよう RLS を追加。
-- （既存の "admin read invite codes"（is_admin）と OR 結合。他人のコードは不可視）
drop policy if exists "own invite codes read" on public.invite_codes;
create policy "own invite codes read" on public.invite_codes
  for select using ((select auth.uid()) = invited_by);

-- ============================================================
-- 適用後の確認（本番で実測済み・2026-07-12）:
--  * 一般ユーザーで create_user_invite() を5回 → 成功、6回目 → limit_reached
--  * 発行コードは全て role=dentist / token_grant_invitee=10 / token_grant_inviter=0
--  * 発行者は自分のコードのみ SELECT 可、他ユーザーのコードは visible=0
--  * 一般ユーザーの invite_codes 直接 INSERT（developer 昇格コード）→ DENIED 42501
-- ============================================================
