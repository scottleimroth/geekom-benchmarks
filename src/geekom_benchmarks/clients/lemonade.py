"""Lemonade OpenAI-compatible client (reference implementation).

Talks to Lemonade's /api/v1 endpoints (llama.cpp Vulkan backend on the GEEKOM).
Uses `requests` for the blocking path and a raw streaming reader for first-token
latency. Designed to degrade gracefully: any transport error is captured as a
ChatResult with ok=False and a categorized error_type, never a raised exception
that would abort a long overnight run.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests

from .base import ChatClient, ChatResult


class LemonadeClient(ChatClient):
    runtime = "lemonade/llamacpp-vulkan"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def list_models(self) -> List[Dict[str, Any]]:
        r = requests.get(f"{self.endpoint}/models", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])

    def model_metadata(self, model_id: str) -> Dict[str, Any]:
        """Return the /models catalog entry for one model id ({} if not found).

        Lemonade exposes `checkpoint`, `recipe`, `recipe_options` (e.g. ctx_size),
        `max_context_window`, `size`, `labels` — but NOT llama.cpp launch params
        like n_gpu_layers / batch / ubatch / flash_attn / file hash. Callers must
        treat absent fields as null-with-reason, not guess.
        """
        try:
            for m in self.list_models():
                if m.get("id") == model_id:
                    return m
        except Exception:
            return {}
        return {}

    def health(self) -> Dict[str, Any]:
        """Best-effort server health/info. Returns {} if unsupported."""
        for path in ("health", "system-info"):
            try:
                r = requests.get(f"{self.endpoint}/{path}", headers=self._headers(), timeout=15)
                if r.ok:
                    return {path: r.json()}
            except Exception:
                continue
        return {}

    def _build_payload(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[str],
        parallel_tool_calls: Optional[bool],
        temperature: float,
        max_tokens: Optional[int],
        stream: bool,
        extra_body: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
            if parallel_tool_calls is not None:
                payload["parallel_tool_calls"] = parallel_tool_calls
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if extra_body:
            payload.update(extra_body)
        return payload

    def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        parallel_tool_calls: Optional[bool] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> ChatResult:
        payload = self._build_payload(
            model, messages, tools, tool_choice, parallel_tool_calls,
            temperature, max_tokens, stream, extra_body,
        )
        if stream:
            return self._chat_stream(payload)
        return self._chat_blocking(payload)

    def _classify_error(self, exc: Exception) -> str:
        if isinstance(exc, requests.Timeout):
            return "timeout"
        return "api_error"

    def _chat_blocking(self, payload: Dict[str, Any]) -> ChatResult:
        t0 = time.time()
        try:
            r = requests.post(
                f"{self.endpoint}/chat/completions",
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=self.timeout,
            )
            elapsed = time.time() - t0
            if not r.ok:
                return ChatResult(
                    ok=False, elapsed_sec=elapsed, error_type="api_error",
                    error_message=f"HTTP {r.status_code}: {r.text[:500]}",
                )
            data = r.json()
        except Exception as exc:  # noqa: BLE001 - intentional broad catch for overnight safety
            return ChatResult(
                ok=False, elapsed_sec=time.time() - t0,
                error_type=self._classify_error(exc),
                error_message=f"{type(exc).__name__}: {exc}",
            )
        return self._parse_response(data, elapsed)

    def _parse_response(self, data: Dict[str, Any], elapsed: float) -> ChatResult:
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
        except (KeyError, IndexError):
            return ChatResult(
                ok=False, elapsed_sec=elapsed, error_type="api_error",
                error_message=f"unexpected response shape: {json.dumps(data)[:400]}",
                raw_response=data,
            )
        usage = data.get("usage") or {}
        content = msg.get("content") or msg.get("reasoning_content") or ""
        return ChatResult(
            ok=True,
            content=content,
            tool_calls=msg.get("tool_calls") or [],
            raw_message=msg,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            tokens_estimated=False,
            elapsed_sec=elapsed,
            finish_reason=choice.get("finish_reason"),
            raw_response=data,
            response_model=data.get("model"),
            system_fingerprint=data.get("system_fingerprint"),
        )

    def _chat_stream(self, payload: Dict[str, Any]) -> ChatResult:
        """Streaming path — measures first-token latency.

        Falls back gracefully if the server doesn't honor SSE; the caller can
        then retry blocking.
        """
        t0 = time.time()
        first_token_at: Optional[float] = None
        content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        usage: Dict[str, Any] = {}
        finish_reason: Optional[str] = None
        resp_model: Optional[str] = None
        fingerprint: Optional[str] = None
        try:
            with requests.post(
                f"{self.endpoint}/chat/completions",
                headers=self._headers(),
                data=json.dumps(payload),
                timeout=self.timeout,
                stream=True,
            ) as r:
                if not r.ok:
                    return ChatResult(
                        ok=False, elapsed_sec=time.time() - t0, error_type="api_error",
                        error_message=f"HTTP {r.status_code}: {r.text[:500]}",
                    )
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    if chunk.get("model"):
                        resp_model = chunk["model"]
                    if chunk.get("system_fingerprint"):
                        fingerprint = chunk["system_fingerprint"]
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    if choices[0].get("finish_reason"):
                        finish_reason = choices[0]["finish_reason"]
                    # Thinking models (gemma-4, Qwen3) stream reasoning_content
                    # before final content. Count the first token of EITHER kind
                    # toward first-token latency.
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        if first_token_at is None:
                            first_token_at = time.time()
                        reasoning_parts.append(reasoning)
                    piece = delta.get("content")
                    if piece:
                        if first_token_at is None:
                            first_token_at = time.time()
                        content_parts.append(piece)
                    if delta.get("tool_calls"):
                        tool_calls.extend(delta["tool_calls"])
        except Exception as exc:  # noqa: BLE001
            return ChatResult(
                ok=False, elapsed_sec=time.time() - t0,
                error_type=self._classify_error(exc),
                error_message=f"{type(exc).__name__}: {exc}",
            )
        elapsed = time.time() - t0
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        ftl = (first_token_at - t0) if first_token_at else None
        comp = usage.get("completion_tokens")
        estimated = False
        if comp is None:
            # usage absent: estimate from BOTH reasoning and final content,
            # since both are generated tokens that count toward throughput.
            comp = self.estimate_tokens(content + reasoning)
            estimated = True
        raw_msg: Dict[str, Any] = {"role": "assistant", "content": content, "tool_calls": tool_calls}
        if reasoning:
            raw_msg["reasoning_content"] = reasoning
        return ChatResult(
            ok=True,
            content=content,
            tool_calls=tool_calls,
            raw_message=raw_msg,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=comp,
            total_tokens=usage.get("total_tokens"),
            tokens_estimated=estimated,
            elapsed_sec=elapsed,
            first_token_latency_sec=round(ftl, 3) if ftl else None,
            finish_reason=finish_reason,
            raw_response={"streamed": True, "usage": usage, "reasoning_chars": len(reasoning)},
            response_model=resp_model,
            system_fingerprint=fingerprint,
        )
