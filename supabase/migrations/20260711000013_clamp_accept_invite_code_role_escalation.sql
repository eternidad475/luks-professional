-- ============================================================
-- Security hardening — migration 13: accept_invite_code() の role 昇格をクランプ
--
-- 背景（潜在的な権限昇格経路）:
--   accept_invite_code()（メール確認済みの authenticated ユーザーなら誰でも
--   /rest/v1/rpc から呼べる公開 RPC）は、招待コードの role を profiles.role へ
--   そのままコピーしていた（現在 'dentist' のユーザーに対して）。
--   is_admin() = role in ('developer','admin') のため、role が 'developer' /
--   'admin' の招待コードが一度でもアクティブになると、そのコード文字列を
--   知る/推測した任意ユーザーが redeem するだけで管理者相当へ昇格できた。
--   （seed された DEV-BETA-0001（developer・推測容易）は revoked 済みで、
--     現時点でアクティブな特権コードは無く、実行可能な脆弱性は無かったが、
--     公開 RPC がコードの秘匿性のみに依存して昇格経路になるのは不適切）
--
-- 修正:
--   accept_invite_code() が付与できる role を「非特権の職種ロール」に限定する。
--   developer / co_developer / admin / owner は本 RPC からは決して付与されず、
--   管理者操作 admin_set_user_role()（is_admin() ゲート済み）経由でのみ設定可能。
--   role 以外のロジック（認証 / メール確認 / revoked / expired / email_mismatch /
--   self_invite / 冪等性 / FOR UPDATE ロック / token_ledger / workspace 加算 /
--   inviter ボーナス）は一切変更していない。
--
-- 変更点は role 代入の CASE 式のみ:
--   before: role = case when role='dentist' then v_inv.role else role end
--   after : role = case when role='dentist'
--                        and v_inv.role in ('dentist','staff','viewer',
--                                           'billing_manager','patient_link_viewer')
--                   then v_inv.role else role end
-- ============================================================

create or replace function public.accept_invite_code(p_code text)
 returns jsonb
 language plpgsql
 security definer
 set search_path to 'public', 'pg_temp'
as $function$
declare
  v_uid       uuid := auth.uid();
  v_email     text;
  v_confirmed timestamptz;
  v_code      text;
  v_inv       public.invite_codes%rowtype;
  v_bal       integer;
  v_inviter_bal integer;
  v_ws        uuid;
  v_inviter_ws uuid;
begin
  if v_uid is null then
    return jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  end if;

  select email, email_confirmed_at into v_email, v_confirmed
    from auth.users where id = v_uid;
  if v_confirmed is null then
    return jsonb_build_object('ok', false, 'reason', 'email_unconfirmed');
  end if;

  v_code := upper(trim(coalesce(p_code, '')));
  if v_code = '' then
    return jsonb_build_object('ok', false, 'reason', 'invalid');
  end if;

  select * into v_inv from public.invite_codes
   where upper(code) = v_code
   for update;
  if v_inv.id is null and position('O' in v_code) > 0 then
    select * into v_inv from public.invite_codes
     where upper(code) = replace(v_code, 'O', '0')
     for update;
  end if;

  if v_inv.id is null then
    return jsonb_build_object('ok', false, 'reason', 'invalid');
  end if;
  if v_inv.revoked_at is not null then
    return jsonb_build_object('ok', false, 'reason', 'revoked');
  end if;
  if v_inv.expires_at is not null and v_inv.expires_at <= now() then
    return jsonb_build_object('ok', false, 'reason', 'expired');
  end if;
  if v_inv.invited_email is not null and lower(v_inv.invited_email) <> lower(coalesce(v_email, '')) then
    return jsonb_build_object('ok', false, 'reason', 'email_mismatch');
  end if;
  if v_inv.invited_by is not null and v_inv.invited_by = v_uid then
    return jsonb_build_object('ok', false, 'reason', 'self_invite');
  end if;

  if exists(select 1 from public.invite_redemptions
             where invite_code_id = v_inv.id and invitee_id = v_uid)
     or exists(select 1 from public.token_ledger
                where user_id = v_uid and reason = 'invitee_initial_beta_grant') then
    update public.profiles
       set beta_access = true,
           trial_tokens_granted = true,
           professional_confirmed = true,
           professional_type = coalesce(professional_type, v_inv.role)
     where id = v_uid;
    return jsonb_build_object('ok', true, 'granted', 0, 'note', 'already_granted');
  end if;

  if v_inv.used_count >= v_inv.max_uses then
    return jsonb_build_object('ok', false, 'reason', 'exhausted');
  end if;

  insert into public.invite_redemptions
    (invite_code_id, invitee_id, inviter_id, invitee_tokens, inviter_tokens)
  values
    (v_inv.id, v_uid, v_inv.invited_by, v_inv.token_grant_invitee,
     case when v_inv.invited_by is not null then v_inv.token_grant_inviter else 0 end);

  update public.invite_codes
     set used_count = used_count + 1,
         accepted_by = v_uid,
         accepted_at = now(),
         updated_at = now()
   where id = v_inv.id;

  update public.profiles
     set beta_access = true,
         trial_tokens_granted = true,
         -- HARDENED: only allow escalation to NON-privileged professional roles.
         -- developer/co_developer/admin/owner are never assignable here; they
         -- must be granted via the admin-gated admin_set_user_role() RPC.
         role = case
                  when role = 'dentist'
                       and v_inv.role in ('dentist','staff','viewer','billing_manager','patient_link_viewer')
                  then v_inv.role
                  else role
                end,
         professional_confirmed = true,
         professional_type = coalesce(professional_type, v_inv.role),
         tokens_remaining = tokens_remaining + v_inv.token_grant_invitee
   where id = v_uid
   returning tokens_remaining into v_bal;

  select id into v_ws from public.workspaces
   where owner_user_id = v_uid and type = 'personal' and deleted_at is null;
  if v_ws is not null then
    update public.workspaces
       set tokens_remaining = tokens_remaining + v_inv.token_grant_invitee,
           updated_at = now()
     where id = v_ws;
  end if;

  insert into public.token_ledger
    (user_id, workspace_id, delta, reason, balance_after, status, idempotency_key)
  values
    (v_uid, v_ws, v_inv.token_grant_invitee, 'invitee_initial_beta_grant', v_bal,
     'confirmed', 'invitee:' || v_inv.id || ':' || v_uid);

  if v_inv.invited_by is not null and v_inv.token_grant_inviter > 0 then
    update public.profiles
       set tokens_remaining = tokens_remaining + v_inv.token_grant_inviter
     where id = v_inv.invited_by
     returning tokens_remaining into v_inviter_bal;
    if found then
      select id into v_inviter_ws from public.workspaces
       where owner_user_id = v_inv.invited_by and type = 'personal' and deleted_at is null;
      if v_inviter_ws is not null then
        update public.workspaces
           set tokens_remaining = tokens_remaining + v_inv.token_grant_inviter,
               updated_at = now()
         where id = v_inviter_ws;
      end if;
      insert into public.token_ledger
        (user_id, workspace_id, delta, reason, balance_after, status, idempotency_key)
      values
        (v_inv.invited_by, v_inviter_ws, v_inv.token_grant_inviter,
         'inviter_referral_beta_bonus', v_inviter_bal, 'confirmed',
         'inviter:' || v_inv.id || ':' || v_uid)
      on conflict (idempotency_key) do nothing;
    end if;
  end if;

  return jsonb_build_object('ok', true, 'granted', v_inv.token_grant_invitee, 'balance', v_bal);
exception when others then
  return jsonb_build_object('ok', false, 'reason', 'db_error', 'code', sqlstate);
end $function$;

-- ============================================================
-- 適用後の確認（本番で実測済み・2026-07-11）:
--  * clamp ロジック単体テスト: dentist + {developer,admin,co_developer,owner}
--    → role は dentist のまま（昇格ブロック）。dentist + {dentist,staff} は許可。
--    developer + dentist → developer 維持（降格なし）。
--  * デプロイ済み関数定義に HARDENED CASE が含まれることを確認。
-- ============================================================
