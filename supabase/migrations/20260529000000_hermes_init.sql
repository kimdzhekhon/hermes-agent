-- Hermes Agent - Supabase 마이그레이션
-- Supabase 대시보드 > SQL Editor에서 실행하세요.

create table if not exists hermes_sessions (
  id text primary key,
  source text,
  user_id text,
  model text,
  model_config text,
  system_prompt text,
  parent_session_id text references hermes_sessions(id) on delete set null,
  started_at float8,
  ended_at float8,
  end_reason text,
  title text,
  created_at timestamptz default now()
);

create table if not exists hermes_messages (
  id bigserial primary key,
  session_id text references hermes_sessions(id) on delete cascade,
  role text not null,
  content text,
  tool_name text,
  tool_calls text,
  tool_call_id text,
  token_count int4,
  finish_reason text,
  created_at timestamptz default now()
);

-- 세션별 메시지 조회 성능용 인덱스
create index if not exists hermes_messages_session_id_idx
  on hermes_messages(session_id, created_at);

-- API 키 / 설정값 저장 테이블
-- Hermes 시작 시 이 테이블의 key=value를 os.environ에 주입함
-- (이미 설정된 Render 환경변수는 덮어쓰지 않음)
create table if not exists hermes_config (
  key text primary key,
  value text not null,
  description text,            -- 사람이 읽을 수 있는 설명 (선택)
  updated_at timestamptz default now()
);

-- 예시 데이터 (주석 해제 후 실제 값으로 변경)
-- insert into hermes_config (key, value, description) values
--   ('OPENROUTER_API_KEY', 'sk-or-...', 'OpenRouter API 키'),
--   ('ANTHROPIC_API_KEY',  'sk-ant-...', 'Anthropic API 키'),
--   ('OPENAI_API_KEY',     'sk-...', 'OpenAI API 키');

-- RLS: 서비스 키(SUPABASE_KEY)로만 접근 허용
alter table hermes_sessions enable row level security;
alter table hermes_messages enable row level security;
alter table hermes_config enable row level security;

-- service_role은 RLS 우회하므로 별도 policy 불필요.
-- anon/authenticated 접근 차단 (선택사항 — 필요시 주석 해제)
-- create policy "deny_anon_sessions" on hermes_sessions for all to anon using (false);
-- create policy "deny_anon_messages" on hermes_messages for all to anon using (false);
-- create policy "deny_anon_config"   on hermes_config   for all to anon using (false);
