-- Checks that RLS keeps two users apart. Changes nothing: it all runs in one transaction
-- that is rolled back at the end.
--
-- 1. Sign in to MedFlow once with each of two Google test accounts (each gets the demo data).
-- 2. Copy both user ids from Authentication -> Users into the two lines marked EDIT below.
-- 3. SQL Editor -> New query -> paste -> Run. Every row of the result should say pass = true.

begin;

create temp table isolation_results (check_name text, expected text, actual text, pass boolean) on commit drop;

do $$
declare
  user_a uuid := '00000000-0000-0000-0000-00000000000a';  -- EDIT: user A's id
  user_b uuid := '00000000-0000-0000-0000-00000000000b';  -- EDIT: user B's id
  results jsonb := '[]';
  n bigint;
  b_has_rows bigint;
begin
  select count(*) into b_has_rows from public.appointments where user_id = user_b;

  -- Act as user A, exactly as the app does: role "authenticated" with A's id in the token.
  perform set_config('request.jwt.claims', json_build_object('sub', user_a, 'role', 'authenticated')::text, true);
  execute 'set local role authenticated';

  select count(*) into n from public.appointments where user_id <> user_a;
  results := results || jsonb_build_object('c', 'A sees no other user''s appointments', 'e', '0', 'a', n, 'p', n = 0);

  select count(*) into n from public.expenses where user_id <> user_a;
  results := results || jsonb_build_object('c', 'A sees no other user''s expenses', 'e', '0', 'a', n, 'p', n = 0);

  update public.expenses set paid_cents = 0 where user_id = user_b;
  get diagnostics n = row_count;
  results := results || jsonb_build_object('c', 'A cannot update B''s expenses', 'e', '0 rows', 'a', n || ' rows', 'p', n = 0);

  delete from public.appointments where user_id = user_b;
  get diagnostics n = row_count;
  results := results || jsonb_build_object('c', 'A cannot delete B''s appointments', 'e', '0 rows', 'a', n || ' rows', 'p', n = 0);

  begin
    insert into public.appointments (user_id, id, date, time, provider, reason, created_at)
      values (user_b, 999999, '2026-11-01', '09:00', 'Test Clinic (fictional)', 'Isolation test', now());
    results := results || jsonb_build_object('c', 'A cannot create rows owned by B', 'e', 'blocked', 'a', 'inserted', 'p', false);
  exception when others then
    results := results || jsonb_build_object('c', 'A cannot create rows owned by B', 'e', 'blocked', 'a', 'blocked (' || sqlstate || ')', 'p', true);
  end;

  begin
    insert into public.expenses (id, date, provider, category, actual_cents, appointment_id, created_at)
      values (999999, '2026-11-01', 'Test Clinic (fictional)', 'other', 100, 999999, now());
    results := results || jsonb_build_object('c', 'A cannot link an expense to an appointment A doesn''t own', 'e', 'blocked', 'a', 'inserted', 'p', false);
  exception when others then
    results := results || jsonb_build_object('c', 'A cannot link an expense to an appointment A doesn''t own', 'e', 'blocked', 'a', 'blocked (' || sqlstate || ')', 'p', true);
  end;

  -- Anonymous visitors (publishable key, not signed in).
  execute 'reset role';
  perform set_config('request.jwt.claims', '{"role": "anon"}', true);
  execute 'set local role anon';
  begin
    select count(*) into n from public.appointments;
    results := results || jsonb_build_object('c', 'Anonymous visitors can''t read appointments', 'e', 'denied', 'a', n || ' rows', 'p', false);
  exception when insufficient_privilege then
    results := results || jsonb_build_object('c', 'Anonymous visitors can''t read appointments', 'e', 'denied', 'a', 'denied', 'p', true);
  end;

  execute 'reset role';
  results := results || jsonb_build_object('c', 'User B has rows to protect (setup check)', 'e', '> 0', 'a', b_has_rows, 'p', b_has_rows > 0);
  insert into isolation_results
    select r->>'c', r->>'e', r->>'a', (r->>'p')::boolean from jsonb_array_elements(results) r;
end $$;

select * from isolation_results;

rollback;
