-- ============================================================
-- CaseFlow Feedback Engine™ / Clinical Curation Loop — Phase 1A
-- 20260718000020_caseflow_feedback_reviews.sql
-- ------------------------------------------------------------
-- ADDITIVE ONLY. Creates a NEW table for structured Good/Bad clinical
-- reviews of generated images / morphing previews. Does NOT modify or
-- overload the existing support/bug `feedback_items` table.
--
-- Reuses the established authorization helper public.is_admin()
-- (role in developer/admin, SECURITY DEFINER, fixed search_path) from
-- 20260701000001_phase1_beta_gate.sql. No new admin mechanism.
--
-- Privacy: no raw patient images, no landmark coordinate arrays. Only
-- structured judgement + non-PHI generation metadata.
-- ============================================================

-- ------------------------------------------------------------
-- 1) caseflow_feedback_reviews
-- ------------------------------------------------------------
create table if not exists public.caseflow_feedback_reviews (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  workspace_id        uuid,
  project_id          uuid,
  case_id             uuid,
  patient_id          uuid,

  -- output lineage (text identifiers, never image binaries)
  output_id           text not null,
  original_output_id  text,
  refined_output_id   text,

  artifact_type       text not null check (artifact_type in ('image','video','preview')),
  studio_module       text not null check (studio_module in ('visual_simulation','morphing_video','photo_manager')),
  rating              text not null check (rating in ('good','bad')),

  reason_tags         text[] not null default '{}',
  comment             text check (comment is null or char_length(comment) <= 2000),

  -- structured non-PHI context (nullable — never block on missing metadata)
  selected_teeth_type jsonb,
  patient_context     jsonb,
  prompt_snapshot     text,
  slider_snapshot     jsonb,
  generation_metadata jsonb,
  model_metadata      jsonb,
  morph_metadata      jsonb,
  token_metadata      jsonb,

  -- consent flags — aggregate learning is OPT-IN and defaults false
  use_for_personalization    boolean not null default true,
  use_for_aggregate_learning boolean not null default false,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- indexes for the admin overview / review-stream queries
create index if not exists cffr_user_idx        on public.caseflow_feedback_reviews(user_id);
create index if not exists cffr_created_idx      on public.caseflow_feedback_reviews(created_at desc);
create index if not exists cffr_output_idx       on public.caseflow_feedback_reviews(output_id);
create index if not exists cffr_module_idx       on public.caseflow_feedback_reviews(studio_module, created_at desc);
create index if not exists cffr_rating_idx       on public.caseflow_feedback_reviews(rating, created_at desc);
create index if not exists cffr_workspace_idx    on public.caseflow_feedback_reviews(workspace_id);
create index if not exists cffr_reason_tags_gin  on public.caseflow_feedback_reviews using gin (reason_tags);

-- keep updated_at fresh on user edits
create or replace function public.tg_cffr_touch_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists cffr_touch_updated_at on public.caseflow_feedback_reviews;
create trigger cffr_touch_updated_at
  before update on public.caseflow_feedback_reviews
  for each row execute function public.tg_cffr_touch_updated_at();

-- ------------------------------------------------------------
-- 2) RLS — users own their rows; admins read all
-- ------------------------------------------------------------
alter table public.caseflow_feedback_reviews enable row level security;

drop policy if exists "cffr user insert own"   on public.caseflow_feedback_reviews;
drop policy if exists "cffr user select own"   on public.caseflow_feedback_reviews;
drop policy if exists "cffr user update own"   on public.caseflow_feedback_reviews;
drop policy if exists "cffr admin read all"    on public.caseflow_feedback_reviews;

-- INSERT: only rows owned by the caller
create policy "cffr user insert own" on public.caseflow_feedback_reviews
  for insert with check ((select auth.uid()) = user_id);

-- SELECT: users read only their own reviews (admins covered by the admin policy below)
create policy "cffr user select own" on public.caseflow_feedback_reviews
  for select using ((select auth.uid()) = user_id);

-- UPDATE: users may edit only their own reviews
create policy "cffr user update own" on public.caseflow_feedback_reviews
  for update using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Admin read-all (separate policy; SELECT is permissive so this ORs with the owner policy)
create policy "cffr admin read all" on public.caseflow_feedback_reviews
  for select using (public.is_admin());

-- No DELETE policy → deletes are denied for everyone (matches feedback_items posture).

-- ------------------------------------------------------------
-- 3) Admin overview RPC (SECURITY DEFINER + is_admin() gate)
--    Returns aggregate counts only — no per-user PHI, no prompts.
-- ------------------------------------------------------------
create or replace function public.admin_feedback_overview()
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  _total   bigint;
  _good    bigint;
  _bad     bigint;
  _recent  bigint;
  _optin   bigint;
  _top_bad jsonb;
  _modules jsonb;
begin
  if not public.is_admin() then
    raise exception 'not_authorized' using errcode = '42501';
  end if;

  select count(*),
         count(*) filter (where rating = 'good'),
         count(*) filter (where rating = 'bad'),
         count(*) filter (where created_at >= now() - interval '7 days'),
         count(*) filter (where use_for_aggregate_learning)
    into _total, _good, _bad, _recent, _optin
    from public.caseflow_feedback_reviews;

  select coalesce(jsonb_agg(t), '[]'::jsonb) into _top_bad from (
    select tag, cnt from (
      select unnest(reason_tags) as tag, count(*) as cnt
        from public.caseflow_feedback_reviews
       where rating = 'bad'
       group by 1 order by 2 desc limit 8
    ) q
  ) t;

  select coalesce(jsonb_agg(m), '[]'::jsonb) into _modules from (
    select studio_module,
           count(*) as total,
           count(*) filter (where rating = 'good') as good,
           count(*) filter (where rating = 'bad')  as bad
      from public.caseflow_feedback_reviews
     group by studio_module
  ) m;

  return jsonb_build_object(
    'total_feedback', coalesce(_total,0),
    'good_count',     coalesce(_good,0),
    'bad_count',      coalesce(_bad,0),
    'good_rate',      case when coalesce(_total,0) > 0 then round((_good::numeric / _total) * 100, 1) else 0 end,
    'bad_rate',       case when coalesce(_total,0) > 0 then round((_bad::numeric  / _total) * 100, 1) else 0 end,
    'top_bad_reasons', _top_bad,
    'module_breakdown', _modules,
    'recent_feedback_count', coalesce(_recent,0),
    'aggregate_learning_opt_in_count', coalesce(_optin,0)
  );
end;
$$;

revoke execute on function public.admin_feedback_overview() from public, anon;
grant  execute on function public.admin_feedback_overview() to authenticated;

-- ------------------------------------------------------------
-- 4) Admin review-stream RPC (filters; admin-gated; no raw prompts)
-- ------------------------------------------------------------
create or replace function public.admin_feedback_reviews(
  p_rating         text default null,
  p_module         text default null,
  p_artifact_type  text default null,
  p_reason_tag     text default null,
  p_date_from      timestamptz default null,
  p_date_to        timestamptz default null,
  p_limit          integer default 50,
  p_offset         integer default 0
)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  _rows jsonb;
  _lim  integer := least(greatest(coalesce(p_limit,50), 1), 200);
  _off  integer := greatest(coalesce(p_offset,0), 0);
begin
  if not public.is_admin() then
    raise exception 'not_authorized' using errcode = '42501';
  end if;

  select coalesce(jsonb_agg(r order by r.created_at desc), '[]'::jsonb) into _rows from (
    select id, created_at, rating, studio_module, artifact_type, reason_tags,
           comment,
           left(output_id, 12) as output_id_short,
           selected_teeth_type,
           (refined_output_id is not null) as has_refinement
      from public.caseflow_feedback_reviews
     where (p_rating        is null or rating        = p_rating)
       and (p_module        is null or studio_module = p_module)
       and (p_artifact_type is null or artifact_type = p_artifact_type)
       and (p_reason_tag    is null or p_reason_tag = any(reason_tags))
       and (p_date_from     is null or created_at >= p_date_from)
       and (p_date_to       is null or created_at <= p_date_to)
     order by created_at desc
     limit _lim offset _off
  ) r;

  return jsonb_build_object('reviews', _rows, 'limit', _lim, 'offset', _off);
end;
$$;

revoke execute on function public.admin_feedback_reviews(text,text,text,text,timestamptz,timestamptz,integer,integer) from public, anon;
grant  execute on function public.admin_feedback_reviews(text,text,text,text,timestamptz,timestamptz,integer,integer) to authenticated;
