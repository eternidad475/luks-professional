-- CASEFLOW STUDIO™
-- Enforce a seven-day lifetime for invite codes, independent of which RPC or
-- server path creates them.
--
-- Safety:
--   * No table or column is dropped.
--   * Existing redeemed/revoked rows are not changed.
--   * Existing active rows with no expiry receive a seven-day grace period
--     starting when this migration is applied.
--   * All future inserts are normalized by a BEFORE INSERT trigger, so a client
--     cannot create a non-expiring or arbitrarily long-lived code.

begin;

create or replace function public.cf_set_invite_code_expiry()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $function$
begin
  -- The product rule is fixed: every newly issued invite is valid for exactly
  -- seven days from the database insertion time. Do not trust client input.
  new.expires_at := now() + interval '7 days';
  return new;
end;
$function$;

revoke all on function public.cf_set_invite_code_expiry() from public;
revoke all on function public.cf_set_invite_code_expiry() from anon;
revoke all on function public.cf_set_invite_code_expiry() from authenticated;

drop trigger if exists cf_invite_codes_set_expiry on public.invite_codes;

create trigger cf_invite_codes_set_expiry
before insert on public.invite_codes
for each row
execute function public.cf_set_invite_code_expiry();

-- Product decision B: preserve every currently active, unused, non-revoked
-- legacy code for a fresh seven-day grace period from migration time. This
-- avoids invalidating older outstanding invitations immediately when the new
-- fixed-expiry rule is introduced. Redeemed/revoked history remains untouched.
update public.invite_codes
set expires_at = now() + interval '7 days'
where expires_at is null
  and revoked_at is null
  and coalesce(used_count, 0) < coalesce(max_uses, 1);

comment on function public.cf_set_invite_code_expiry() is
  'CASEFLOW: normalizes every newly issued invite code to a seven-day lifetime.';

commit;