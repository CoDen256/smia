"""
registry.py — the provider registry: which provider adapters are configured
per kind (D-S7's shortlists, wired up as adapters.* modules call `register`
at import time).

This is declarative config, not code paths (per CLAUDE.md's hard boundary):
`GET /providers` (provider-catalog) reads straight off this registry, and the
lookup-cache runner uses it to resolve "which adapter answers this request"
and to enforce "provider required unless exactly one is configured".
"""

from __future__ import annotations

KINDS = ("inflections", "ipa", "tts", "translations", "stt")


class UnknownKindError(Exception):
    pass


class UnknownProviderError(Exception):
    def __init__(self, kind: str, provider: str, available: list[str]):
        self.kind = kind
        self.provider = provider
        self.available = available
        super().__init__(f"unknown provider {provider!r} for kind {kind!r}; available: {available}")


class ProviderRequiredError(Exception):
    def __init__(self, kind: str, available: list[str]):
        self.kind = kind
        self.available = available
        super().__init__(f"provider required for kind {kind!r}; available: {available}")


class ProviderRegistry:
    def __init__(self):
        self._adapters: dict[str, dict[str, object]] = {}
        self._available: dict[tuple[str, str], object] = {}

    def register(self, kind: str, name: str, adapter, *, available=None) -> None:
        """`available`, if given, is a zero-arg callable re-checked on every
        listing/resolution (not just at import time) — e.g. `lambda:
        bool(os.environ.get("X_TOKEN"))` — so a provider whose required
        credential isn't configured is dynamically excluded from
        `providers_for`/`resolve_provider` without needing a code change or
        restart once the token is set. Omit for providers with no such
        precondition (always available)."""
        self._adapters.setdefault(kind, {})[name] = adapter
        if available is not None:
            self._available[(kind, name)] = available

    def providers_for(self, kind: str) -> list[str]:
        return sorted(
            name
            for name in self._adapters.get(kind, {})
            if self._available.get((kind, name), lambda: True)()
        )

    def adapter_for(self, kind: str, name: str):
        return self._adapters.get(kind, {})[name]

    def resolve_provider(self, kind: str, requested: str | None) -> str:
        """Implements the lookup-cache 'exactly one provider per request' rule:
        required when 2+ providers are configured, optional (defaulted) when
        exactly one is."""
        available = self.providers_for(kind)
        if requested is not None:
            if requested not in available:
                raise UnknownProviderError(kind, requested, available)
            return requested
        if len(available) == 1:
            return available[0]
        raise ProviderRequiredError(kind, available)


registry = ProviderRegistry()
