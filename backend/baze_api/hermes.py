"""Talk to one app's Hermes API server. The browser never calls this."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class HermesError(RuntimeError):
    pass


class HermesClient:
    def complete(self, *, base_url: str, api_key: str, content: str, session_id: str | None) -> tuple[str, str]:
        payload = {"model": "hermes-agent", "messages": [{"role": "user", "content": content}]}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = response.read()
                session = response.headers.get("X-Hermes-Session-Id") or session_id or ""
        except urllib.error.HTTPError as exc:
            raise HermesError(exc.read().decode("utf-8", "replace")[:300]) from exc
        except OSError as exc:
            raise HermesError(str(exc)) from exc
        try:
            body = json.loads(raw.decode("utf-8"))
            text = body["choices"][0]["message"]["content"]
        except (UnicodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise HermesError("Hermes returned an unreadable reply") from exc
        if not isinstance(text, str) or not text.strip():
            raise HermesError("Hermes returned an empty reply")
        if not session:
            raise HermesError("Hermes did not return a session id")
        return text, session
