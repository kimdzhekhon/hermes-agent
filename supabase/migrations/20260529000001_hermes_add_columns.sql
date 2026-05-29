-- hermes_sessions 누락 컬럼 추가
alter table hermes_sessions
  add column if not exists message_count int4 default 0,
  add column if not exists tool_call_count int4 default 0,
  add column if not exists input_tokens int4 default 0,
  add column if not exists output_tokens int4 default 0,
  add column if not exists cache_read_tokens int4 default 0,
  add column if not exists cache_write_tokens int4 default 0,
  add column if not exists reasoning_tokens int4 default 0,
  add column if not exists api_call_count int4 default 0,
  add column if not exists estimated_cost_usd float8,
  add column if not exists actual_cost_usd float8;
