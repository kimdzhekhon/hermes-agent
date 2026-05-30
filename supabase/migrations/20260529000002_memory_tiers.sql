-- 메모리 계층 시스템
-- hermes_sessions에 memory_tier 추가 (short: 7일 후 삭제, long: 영구 보존)
ALTER TABLE hermes_sessions
  ADD COLUMN IF NOT EXISTS memory_tier text DEFAULT 'short'
  CHECK (memory_tier IN ('short', 'long'));

-- 헤르메스가 직접 관리하는 기억 테이블
-- persona: 절대 삭제 금지 (USER.md 백업)
-- long:    영구 보존 (MEMORY.md 백업)
CREATE TABLE IF NOT EXISTS hermes_memories (
  key     text PRIMARY KEY,            -- 'MEMORY.md' | 'USER.md' | 사용자 정의 키
  tier    text NOT NULL DEFAULT 'long'
            CHECK (tier IN ('persona', 'long')),
  content text NOT NULL DEFAULT '',
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE hermes_memories ENABLE ROW LEVEL SECURITY;

-- pg_net, pg_cron 활성화
CREATE EXTENSION IF NOT EXISTS pg_net  WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;

-- 5분마다 Render 깨우기
-- 사전 조건: hermes_config에 RENDER_URL 키 추가 필요
--   INSERT INTO hermes_config (key, value, description)
--   VALUES ('RENDER_URL', 'https://hermes-agent-private.onrender.com', 'Render 서비스 URL')
--   ON CONFLICT (key) DO NOTHING;
SELECT cron.schedule(
  'hermes-keepalive',
  '*/5 * * * *',
  $$
  SELECT net.http_get(
    url := (SELECT value || '/health' FROM hermes_config WHERE key = 'RENDER_URL')
  )
  WHERE EXISTS (SELECT 1 FROM hermes_config WHERE key = 'RENDER_URL')
  $$
);

-- 매일 새벽 3시 (KST = UTC+9 → UTC 18:00 전날)
-- short tier + 7일 지난 세션 삭제 (cascade → hermes_messages도 자동 삭제)
SELECT cron.schedule(
  'hermes-memory-cleanup',
  '0 18 * * *',
  $$
  DELETE FROM hermes_sessions
  WHERE memory_tier = 'short'
    AND created_at < now() - interval '7 days'
  $$
);
