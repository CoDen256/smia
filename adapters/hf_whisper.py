"""
adapters/hf_whisper.py — the `hf_whisper` /stt provider, ported from
phonexa's `shadow.js` `transcribeViaHuggingFace` (task 7.1): Hugging Face
Inference, cloud-only per D17 (no local faster-whisper fallback —
`shadow.js`'s local-backend option is explicitly dropped, per the
proposal's Impact section).

Uses `huggingface_hub`'s `InferenceClient` (D-L1, `provider-client-
libraries`) rather than hand-rolled `requests` calls against
`router.huggingface.co` — HF's own maintained client, which already
handles the base64/raw-bytes request-shape branching `shadow.js`'s
original code hand-rolled: `extra_body={"generate_kwargs": {...}}` is the
client's documented passthrough for provider-specific Inference
parameters, confirmed against a live call to produce the same
`language`/`task` behavior as the original JSON body.

Input is raw audio bytes (not JSON) — see `app.py`'s `/stt` route for how
that's reconciled with the lookup-cache's JSON-input-hashing contract.
"""

from __future__ import annotations

import base64
import os

from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError

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

        extra_body = None
        if language:
            extra_body = {"generate_kwargs": {"language": language, "task": "transcribe"}}

        client = InferenceClient(token=token)
        try:
            output = client.automatic_speech_recognition(audio, model=model, extra_body=extra_body)
        except HfHubHTTPError as exc:
            message = exc.server_message or str(exc)
            if "loading" in message.lower():
                raise ProviderLookupError(
                    f"model is loading on Hugging Face's servers — try again shortly ({message})"
                ) from exc
            raise ProviderLookupError(f"hf_whisper request failed: {message}") from exc
        except Exception as exc:  # the client's own exceptions (timeouts, etc.)
            raise ProviderLookupError(f"hf_whisper request failed: {exc}") from exc

        return {"text": output.text or ""}


registry.register(
    "stt", "hf_whisper", HfWhisperAdapter(), available=lambda: bool(os.environ.get("HF_TOKEN"))
)
