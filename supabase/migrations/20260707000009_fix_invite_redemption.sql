-- ============================================================
-- Hotfix — migration 9: 招待コード承認が反映されない不具合の修正
--
-- 根本原因（実証済み）:
--   token_ledger_idempotency_idx が partial unique index
--   （WHERE idempotency_key IS NOT NULL）のため、
--   accept_invite_code / refund_generation_tokens 内の
--   `on conflict (idempotency_key)` が index を推論できず
--   「there is no unique or exclusion constraint matching the
--    ON CONFLICT specification」で実行時エラー → 全体 rollback。
--   inviter ボーナス分岐（invited_by あり・token_grant_inviter>0）を
--   通る招待コードは全て承認不能だった。
--
-- 修正:
--  1) index を全行 unique に置換（NULL は NULLS DISTINCT で複数可 = 実質同義。
--     これで既存の on conflict 句が accept_invite_code / refund_generation_tokens
--     の両方でそのまま動く）
--  2) accept_invite_code v2:
--     - db エラー時に generic 500 ではなく reason='db_error' を返す
--     - email 未確認チェック（reason='email_unconfirmed'）
--     - O/0 誤入力フォールバック（完全一致が無い場合のみ O→0 で再検索。
--       生成コードは16進のため O を含まず、誤置換は構造的に起きない）
--     - 承認時に professional_confirmed=true /
--       professional_type=coalesce(既存値, invite_codes.role) も反映
--       （職種の localStorage 反映は unlock 後にしか走らないため RPC 側で担保）
--     - migration 7 対応: token_ledger.workspace_id に personal workspace を
--       スタンプし、workspaces.tokens_remaining（mirror）にも加算
--       （2.1b までは profiles が「正」— mirror は 2.1b のコピーで上書きされる）
--     - 既承認ユーザーの再実行は状態修復（beta_access 等）のみ行い ok を返す
-- ============================================================

-- ------------------------------------------------------------
-- 1) idempotency index: partial → full unique（重複なしは確認済み）
-- ------------------------------------------------------------
drop index if exists public.token_ledger_idempotency_idx;
create unique index token_ledger_idempotency_idx
  on public.token_ledger(idempotency_key);

-- ------------------------------------------------------------
-- 2) accept_invite_code v2
-- ------------------------------------------------------------
create or replace function public.accept_invite_code(p_code text)
returns jsonb
language plpgsql security definer set search_path = public, pg_temp
as $$
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
  -- O/0 誤入力フォールバック: 完全一致が無い場合のみ O→0 で再検索
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

  -- 既にこのユーザーが承認済み → 状態修復のみ（後追い再実行を許容）
  if exists(select 1 from public.invite_redemptions
             where invite_code_id = v_inv.id and invitee_id = v_uid)
     or exists(select 1 from public.token_ledger
                where user_id = v_uid and reason = 'invitee_initial_beta_grant') then
    update public.profiles
       set beta_access = true,
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
         role = case when role = 'dentist' then v_inv.role else role end,
         professional_confirmed = true,
         professional_type = coalesce(professional_type, v_inv.role),
         tokens_remaining = tokens_remaining + v_inv.token_grant_invitee
   where id = v_uid
   returning tokens_remaining into v_bal;

  -- migration 7 対応: personal workspace への紐付けと mirror 加算
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
  -- 予期しないDBエラーは rollback 済み。frontend が具体的な案内を出せるよう構造化して返す
  return jsonb_build_object('ok', false, 'reason', 'db_error', 'code', sqlstate);
end $$;

revoke execute on function public.accept_invite_code(text) from public, anon;
grant  execute on function public.accept_invite_code(text) to authenticated;

-- ============================================================
-- 備考: refund_generation_tokens の on conflict も同じ index 起因で
-- 実行時エラーになっていたが、1) の index 置換のみで解消（body 変更不要）。
-- ============================================================
