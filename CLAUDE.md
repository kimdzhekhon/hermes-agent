# Hermes Agent

## Supabase
- 계정: `supa-hermes` (키체인: `supabase-hermes`)
- 마이그레이션: `supabase_migration.sql`
- 테이블: `hermes_sessions`, `hermes_messages`, `hermes_config`

## 배포
- 플랫폼: Render (Docker)
- 레포: `kimdzhekhon/hermes-agent-private` (private)
- Render 환경변수: `SUPABASE_URL`, `SUPABASE_KEY` 2개만 설정
- 나머지 키(`DISCORD_BOT_TOKEN`, `OPENROUTER_API_KEY` 등)는 Supabase `hermes_config` 테이블에서 관리
