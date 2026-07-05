-- ============================================================
-- migration 17: 管理者は招待コード発行数を無制限に
--
-- 目的: create_user_invite()（一般ユーザー向け新規ユーザー招待）で、
--   admin（is_admin() = role developer/admin）だけは「同時に有効な未使用コード
--   最大5件」の上限を免除し、無制限に発行できるようにする。
--   一般ユーザー（非admin）は従来どおり5件上限を維持する。
--
--   変更点は上限チェック 1 箇所のみ。発行されるコード内容（role=dentist /
--   token_grant_invitee=10 / token_grant_inviter=0 / max_uses=1）や RLS、
--   execute grant は一切変えない。admin であっても本 RPC 経由の発行は
--   dentist 固定で、developer 昇格コードは発行できない（従来通り
--   admin_create_invite_code 経由のみ）。
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

  -- 同時に有効な未使用コードは最大5件（使用済み/失効/revoke済みは数えない）。
  -- ただし admin（developer/admin）は上限免除で無制限に発行できる。
  select count(*) into v_active from public.invite_codes
   where invited_by = v_uid
     and revoked_at is null
     and used_count < max_uses
     and (expires_at is null or expires_at > now());
  if not public.is_admin() and v_active >= 5 then
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

-- ============================================================
-- 適用後の確認（本番）:
--  * admin（developer/admin）で create_user_invite() を6回以上 → 全て成功（上限なし）
--  * 一般ユーザーは6回目 → limit_reached（従来通り5件上限）
--  * admin 発行コードも role=dentist / invitee=10 / inviter=0 で固定
-- ============================================================
