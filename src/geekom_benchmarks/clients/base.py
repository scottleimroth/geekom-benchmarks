"""Provider-neutral chat client interface.

Hardware/runtime specifics live behind this adapter. A new backend (Ollama,
LM Studio, NVIDIA, Apple) only has to implement `ChatClient`; runners never see
provider details. The reference implementation is `LemonadeClient`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChatResult:
    """Normalized result of one chat/completions call."""

    ok: bool
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_message: Dict[str, Any] = field(default_factory=dict)
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_estimated: bool = False
    elapsed_sec: float = 0.0
    first_token_latency_sec: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    # Provenance straight from the server response (used for llama-bench fields).
    response_model: Optional[str] = None      # e.g. "gemma-4-E2B-it-Q4_K_M.gguf"
    system_fingerprint: Optional[str] = None  # e.g. "b9253-29f148222" (llama.cpp build)


class ChatClient:
    """Abstract OpenAI-compatible chat client."""

    def __init__(self, endpoint: str, api_key: str = "lemonade", timeout: int = 300):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def list_models(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def is_reachable(self) -> bool:
        try:
            self.list_models()
            return True
        except Exception:
            return False

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
        raise NotImplementedError

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Heuristic ~4 chars/token fallback when the API reports no usage."""
        return max(1, round(len(text or "") / 4))
