-- ─────────────────────────────────────────────────────────────
-- Fintoc Finance App — Supabase Schema
-- Run this in your Supabase project: SQL Editor → New Query
-- ─────────────────────────────────────────────────────────────

-- 1. Links: each user's Fintoc connection
create table if not exists public.links (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  link_token  text not null,
  institution text,
  created_at  timestamptz default now()
);

-- 2. Movements: all bank movements per user
create table if not exists public.movements (
  id               text primary key,   -- Fintoc's movement id (e.g. mov_xxx)
  user_id          uuid not null references auth.users(id) on delete cascade,
  link_id          uuid references public.links(id) on delete cascade,
  amount           bigint not null,
  currency         text default 'CLP',
  post_date        timestamptz,
  transaction_date timestamptz,
  description      text,
  type             text,
  pending          boolean default false,
  reference_id     text,
  comment          text,
  account_name     text,
  sender_data      jsonb,
  recipient_data   jsonb,
  raw              jsonb,
  created_at       timestamptz default now()
);

-- 3. Indexes for fast queries
create index if not exists movements_user_id_idx      on public.movements(user_id);
create index if not exists movements_post_date_idx    on public.movements(post_date desc);
create index if not exists movements_user_date_idx    on public.movements(user_id, post_date desc);

-- ─── Row Level Security ────────────────────────────────────────

alter table public.links     enable row level security;
alter table public.movements enable row level security;

-- Links: users can only see/modify their own
create policy "links: user owns" on public.links
  for all using (auth.uid() = user_id);

-- Movements: users can only see their own
create policy "movements: user owns" on public.movements
  for all using (auth.uid() = user_id);
