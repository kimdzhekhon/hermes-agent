"""
Supabase sync layer for Hermes sessions and messages.

SQLite를 로컬 캐시로 유지하면서 Supabase에 듀얼 라이트.
SUPABASE_URL, SUPABASE_KEY 환경변수가 없으면 아무것도 하지 않음.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()
_client_init_attempted = False


def _get_client():
    global _client, _client_init_attempted
    if _client_init_attempted:
        return _client
    with _client_lock:
        if _client_init_attempted:
            return _client
        _client_init_attempted = True
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        if not url or not key:
            return None
        try:
            from supabase import create_client
            _client = create_client(url, key)
            logger.info("Supabase 클라이언트 초기화 완료")
        except Exception as e:
            logger.warning("Supabase 클라이언트 초기화 실패: %s", e)
            _client = None
        return _client


def _run_in_background(fn, *args):
    """best-effort 백그라운드 실행 — 실패해도 무시"""
    t = threading.Thread(target=fn, args=args, daemon=True)
    t.start()


def sync_session(
    session_id: str,
    source: str,
    user_id: Optional[str] = None,
    model: Optional[str] = None,
    model_config: Optional[Any] = None,
    system_prompt: Optional[str] = None,
    parent_session_id: Optional[str] = None,
    started_at: Optional[float] = None,
) -> None:
    """세션 row를 Supabase sessions 테이블에 upsert (백그라운드)."""
    _run_in_background(
        _do_sync_session,
        session_id, source, user_id, model,
        model_config, system_prompt, parent_session_id,
        started_at or time.time(),
    )


def _do_sync_session(
    session_id, source, user_id, model,
    model_config, system_prompt, parent_session_id, started_at,
):
    client = _get_client()
    if not client:
        return
    try:
        client.table("hermes_sessions").upsert({
            "id": session_id,
            "source": source,
            "user_id": user_id,
            "model": model,
            "model_config": json.dumps(model_config) if model_config else None,
            "system_prompt": system_prompt,
            "parent_session_id": parent_session_id,
            "started_at": started_at,
        }, on_conflict="id").execute()
    except Exception as e:
        logger.debug("Supabase session sync 실패 (%s): %s", session_id, e)


def sync_message(
    session_id: str,
    role: str,
    content: Optional[Any] = None,
    tool_name: Optional[str] = None,
    tool_calls: Optional[Any] = None,
    tool_call_id: Optional[str] = None,
    token_count: Optional[int] = None,
    finish_reason: Optional[str] = None,
) -> None:
    """메시지를 Supabase messages 테이블에 insert (백그라운드)."""
    # content가 list(멀티모달)이면 JSON 직렬화
    stored_content = (
        json.dumps(content) if isinstance(content, (list, dict)) else content
    )
    _run_in_background(
        _do_sync_message,
        session_id, role, stored_content,
        tool_name, json.dumps(tool_calls) if tool_calls else None,
        tool_call_id, token_count, finish_reason,
    )


def _do_sync_message(
    session_id, role, content,
    tool_name, tool_calls_json, tool_call_id,
    token_count, finish_reason,
):
    client = _get_client()
    if not client:
        return
    try:
        client.table("hermes_messages").insert({
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "tool_calls": tool_calls_json,
            "tool_call_id": tool_call_id,
            "token_count": token_count,
            "finish_reason": finish_reason,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).execute()
    except Exception as e:
        logger.debug("Supabase message sync 실패 (%s/%s): %s", session_id, role, e)


def update_session_end(session_id: str, ended_at: float, end_reason: str) -> None:
    """세션 종료 정보를 Supabase에 업데이트 (백그라운드)."""
    _run_in_background(_do_update_session_end, session_id, ended_at, end_reason)


def _do_update_session_end(session_id, ended_at, end_reason):
    client = _get_client()
    if not client:
        return
    try:
        client.table("hermes_sessions").update({
            "ended_at": ended_at,
            "end_reason": end_reason,
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.debug("Supabase session end 업데이트 실패 (%s): %s", session_id, e)


def load_config_from_supabase() -> int:
    """Supabase hermes_config 테이블에서 키-값을 읽어 os.environ에 주입.

    이미 설정된 환경변수는 덮어쓰지 않음 (Render 환경변수 > Supabase 설정 우선순위).
    SUPABASE_URL, SUPABASE_KEY가 없으면 아무것도 하지 않음.
    반환값: 주입된 키 개수.
    """
    client = _get_client()
    if not client:
        return 0
    try:
        resp = client.table("hermes_config").select("key,value").execute()
        injected = 0
        for row in resp.data or []:
            k, v = row.get("key", ""), row.get("value", "")
            if k and k not in os.environ:
                os.environ[k] = v
                injected += 1
        if injected:
            logger.info("Supabase에서 %d개 환경변수 로드됨", injected)
        return injected
    except Exception as e:
        logger.warning("Supabase config 로드 실패: %s", e)
        return 0


def load_memories(tier: Optional[str] = None) -> list:
    """hermes_memories 테이블에서 기억 로드.

    tier 지정 시 해당 tier만 반환, 없으면 전체 반환.
    반환값: [{"key": ..., "tier": ..., "content": ...}, ...]
    """
    client = _get_client()
    if not client:
        return []
    try:
        query = client.table("hermes_memories").select("key,tier,content")
        if tier:
            query = query.eq("tier", tier)
        resp = query.execute()
        return resp.data or []
    except Exception as e:
        logger.debug("Supabase 메모리 로드 실패: %s", e)
        return []


def upsert_memory(tier: str, key: str, content: str) -> bool:
    """메모리를 Supabase hermes_memories에 저장/업데이트 (동기).

    tier: 'persona' | 'long'
    key:  'MEMORY.md' | 'USER.md' | 사용자 정의 키
    반환값: 성공 여부
    """
    client = _get_client()
    if not client:
        return False
    try:
        client.table("hermes_memories").upsert({
            "key": key,
            "tier": tier,
            "content": content,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, on_conflict="key").execute()
        return True
    except Exception as e:
        logger.debug("Supabase 메모리 upsert 실패 (%s): %s", key, e)
        return False


def set_session_memory_tier(session_id: str, tier: str) -> None:
    """세션의 memory_tier를 변경 (백그라운드). tier: 'short' | 'long'"""
    _run_in_background(_do_set_session_memory_tier, session_id, tier)


def _do_set_session_memory_tier(session_id: str, tier: str):
    client = _get_client()
    if not client:
        return
    try:
        client.table("hermes_sessions").update(
            {"memory_tier": tier}
        ).eq("id", session_id).execute()
    except Exception as e:
        logger.debug("Supabase session memory_tier 변경 실패 (%s): %s", session_id, e)


def update_session_title(session_id: str, title: str) -> None:
    """세션 제목을 Supabase에 업데이트 (백그라운드)."""
    _run_in_background(_do_update_session_title, session_id, title)


def _do_update_session_title(session_id, title):
    client = _get_client()
    if not client:
        return
    try:
        # title=None이면 NULL로 업데이트 (SQLite와 일치)
        client.table("hermes_sessions").update({"title": title}).eq("id", session_id).execute()
    except Exception as e:
        logger.debug("Supabase session title 업데이트 실패 (%s): %s", session_id, e)
