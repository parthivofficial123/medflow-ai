-- MedFlow AI demo schema. Fictional data only.
-- Run once in the Supabase dashboard: SQL Editor -> New query -> paste -> Run.
-- It only creates things; it never drops or deletes. If a table already exists it stops with an error.
--
-- Every row belongs to one signed-in user. Ids are counted per user (primary key user_id + id),
-- so the app's storage.next_id() and URLs like /appointments/3 keep working.

create table public.appointments (
  user_id              uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id                   bigint not null check (id > 0),
  date                 date not null,
  time                 text not null check (time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  provider             text not null check (char_length(provider) between 1 and 100),
  location             text not null default '' check (char_length(location) <= 120),
  reason               text not null check (char_length(reason) between 1 and 120),
  notes                text not null default '' check (char_length(notes) <= 1000),
  status               text not null default 'scheduled'
                       check (status in ('scheduled', 'completed', 'cancelled')),
  reminder_days_before smallint check (reminder_days_before in (0, 1, 2, 3, 7)),
  reminder_dismissed   boolean not null default false,
  tasks                jsonb not null default '[]'::jsonb check (jsonb_typeof(tasks) = 'array'),
  created_at           timestamp not null,
  updated_at           timestamp,
  primary key (user_id, id)
);

create table public.expenses (
  user_id           uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id                bigint not null check (id > 0),
  date              date not null,
  provider          text not null check (char_length(provider) between 1 and 100),
  description       text not null default '' check (char_length(description) <= 200),
  category          text not null check (category in
                    ('visit', 'imaging', 'lab', 'pharmacy', 'dental', 'vision', 'therapy', 'other')),
  estimated_cents   integer check (estimated_cents between 0 and 100000000),  -- null = no estimate
  actual_cents      integer check (actual_cents between 0 and 100000000),     -- null = not billed yet; 0 = a $0 bill
  paid_cents        integer not null default 0 check (paid_cents between 0 and 100000000),
  appointment_id    bigint,
  appointment_label text,
  source            text check (source = 'bill'),
  created_at        timestamp not null,
  updated_at        timestamp,
  primary key (user_id, id),
  -- An expense can only link to its owner's appointment. Deleting the appointment clears
  -- just the link (the label stays), matching the app's own unlink-then-delete order.
  foreign key (user_id, appointment_id) references public.appointments (user_id, id)
    on delete set null (appointment_id),
  check (estimated_cents is not null or actual_cents is not null),
  check (actual_cents is null or paid_cents <= actual_cents)
);
create index expenses_appointment_idx on public.expenses (user_id, appointment_id);

-- Row-Level Security: a signed-in user sees and changes only their own rows. The app uses the
-- publishable key plus the user's access token, so these policies are what keep users apart.
alter table public.appointments enable row level security;
alter table public.expenses enable row level security;

revoke all on public.appointments, public.expenses from anon, authenticated;
grant select, insert, update, delete on public.appointments, public.expenses to authenticated;

create policy "own appointments: select" on public.appointments for select to authenticated
  using (user_id = (select auth.uid()));
create policy "own appointments: insert" on public.appointments for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy "own appointments: update" on public.appointments for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own appointments: delete" on public.appointments for delete to authenticated
  using (user_id = (select auth.uid()));

create policy "own expenses: select" on public.expenses for select to authenticated
  using (user_id = (select auth.uid()));
create policy "own expenses: insert" on public.expenses for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy "own expenses: update" on public.expenses for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own expenses: delete" on public.expenses for delete to authenticated
  using (user_id = (select auth.uid()));
