-- ============================================================
-- Run this ONCE in Supabase → SQL Editor
-- ============================================================

-- Places table
create table if not exists places (
  id                 text primary key,
  name               text not null,
  latitude           float8 not null,
  longitude          float8 not null,
  distance_from_isb  int not null,
  drive_time         text,
  difficulty         text,
  description        text,
  recommended_days   int default 1
);

-- Images table (url is unique so cron never inserts duplicates)
create table if not exists place_images (
  id          uuid primary key default gen_random_uuid(),
  place_id    text references places(id) on delete cascade,
  url         text unique not null,
  source      text,          -- 'wikimedia' | 'flickr'
  width       int,
  height      int,
  license     text,
  fetched_at  timestamptz default now(),
  is_approved boolean default true
);

create index if not exists idx_place_images_place_id on place_images(place_id);

-- Row Level Security: app can read, only service key can write
alter table places       enable row level security;
alter table place_images enable row level security;

create policy "public read places"
  on places for select using (true);

create policy "public read approved images"
  on place_images for select using (is_approved = true);

-- Seed all places
insert into places values
  ('islamabad',    'Islamabad',       33.6996, 73.0363,  0,   'Starting point',        'Easy',     'Capital city, gateway to all northern tours.',                          1),
  ('murree',       'Murree',          33.9070, 73.3943,  65,  '1.5 hrs',               'Easy',     'Pakistan''s most beloved hill station at 2,200m.',                       1),
  ('nathiagali',   'Nathia Gali',     34.0729, 73.3812,  90,  '2 hrs',                 'Easy',     'Misty Galiyat highlands at 2,500m. Cooler than Murree.',                 1),
  ('kaghan',       'Kaghan Valley',   34.5417, 73.3500,  220, '5-6 hrs',               'Moderate', 'Glacial lakes, alpine meadows, and Babusar Pass at 4,173m.',             3),
  ('swat',         'Swat Valley',     35.2227, 72.4258,  250, '5 hrs',                 'Moderate', 'The Switzerland of Pakistan. Green mountains and crystal rivers.',        3),
  ('chitral',      'Chitral',         35.8540, 71.7866,  380, '8-9 hrs',               'Hard',     'Gateway to the Kalash tribe with unique pre-Islamic culture.',            4),
  ('fairymeadows', 'Fairy Meadows',   35.3832, 74.5717,  480, '9-10 hrs+jeep+hike',   'Hard',     'Magical meadows directly below Nanga Parbat (8,126m).',                  3),
  ('gilgit',       'Gilgit',          35.9202, 74.3080,  600, '12-14 hrs',             'Hard',     'Major KKH junction. Left for Hunza, right for Skardu.',                  1),
  ('hunza',        'Hunza Valley',    36.3167, 74.6500,  650, '14-16 hrs',             'Hard',     'Crown jewel of Pakistan tourism. Attabad Lake and Passu Cones.',          5),
  ('skardu',       'Skardu',          35.3247, 75.5510,  700, '15-18 hrs or 1hr fly', 'Hard',     'Gateway to K2 (8,611m) and Deosai Plains.',                              4)
on conflict (id) do nothing;
