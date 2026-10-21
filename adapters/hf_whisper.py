"""
adapters/hf_whisper.py — the `hf_whisper` /stt provider, ported from
phonexa's `shadow.js` `transcribeViaHuggingFace` (task 7.1): Hugging Face
Inference's router, cloud-only per D17 (no local faster-whisper fallback —
`shadow.js`'s local-backend option is explicitly dropped, per the
proposal's Impact section).

Input is raw audio bytes (not JSON) — see `app.py`'s `/stt` route for how
that's reconciled with the lookup-cache's JSON-input-hashing contract.
`language`, when given, switches HF's request shape from raw-bytes body to
a JSON body with base64-encoded audio (mirrors `shadow.js` exactly: HF's
generate_kwargs.language option isn't available on the plain-bytes path).
"""

from __future__ import annotations

import base64
import os

import requests

from cache import ProviderLookupError
from registry import registry

_DEFAULT_MODEL = "openai/whisper-large-v3"


class HfWhisperAdapter:
    def lookup(self, input_dict: dict) -> dict:
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise ProviderLookupError("hf_whisper is not configured yet: needs an HF_TOKEN")

        audio = base64.b64decode(input_dict["audio_b64"])
        language = input_dict.get("lang")
        model = os.environ.get("HF_WHISPER_MODEL", _DEFAULT_MODEL)
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        headers = {"Authorization": f"Bearer {token}"}

        if language:
            headers["Content-Type"] = "application/json"
            body = {
                "inputs": base64.b64encode(audio).decode("ascii"),
                "parameters": {"generate_kwargs": {"language": language, "task": "transcribe"}},
            }
            kwargs = {"json": body}
        else:
            headers["Content-Type"] = "audio/wav"
            kwargs = {"data": audio}

        try:
            resp = requests.post(url, headers=headers, timeout=60, **kwargs)
            data = resp.json() if resp.content else None
        except (requests.RequestException, ValueError) as exc:
            raise ProviderLookupError(f"hf_whisper request failed: {exc}") from exc

        if not resp.ok:
            error = (data or {}).get("error")
            if error and "loading" in error.lower():
                eta = (data or {}).get("estimated_time", 20)
                raise ProviderLookupError(
                    f"model is loading on Hugging Face's servers (~{eta:.0f}s) — try again shortly"
                )
            raise ProviderLookupError(error or f"HTTP {resp.status_code}")

        return {"text": (data or {}).get("text", "")}


registry.register("stt", "hf_whisper", HfWhisperAdapter())
