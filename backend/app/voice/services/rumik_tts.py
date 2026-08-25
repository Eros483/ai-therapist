"""Rumik Silk TTS — Mulberry (description-driven) and Muga (tone tags), §8.3.

Thin HTTP client over Rumik Silk's TTS endpoint. Rumik is paused in this
environment (no free tier, no key) — the live API is never called here; the
transport is injected (``httpx.AsyncClient``) and exercised through mocks in
tests, and behind a real key at eval time.

Boundary behavior, per the design contract:
- **Script (§2.2):** Mulberry expects Hindi in Devanagari and English in
  Latin, so canonical romanized text is transliterated at this boundary via
  ``script.romanized_to_devanagari`` (v0 best-effort table).
- **Prosody (§7.7):** Mulberry is description-driven, so the phase directive
  map merges into the ``description`` param rather than per-parameter knobs.

On any transport/HTTP error it logs and yields nothing — a failed synthesis
must not crash the voice loop.
"""

from collections.abc import AsyncIterator

import httpx

from app.config.settings import settings
from app.logger import logger
from app.voice.services.script import romanized_to_devanagari


class _RumikSilkTTS:
    """Shared HTTP shape for Mulberry and Muga."""

    _model = "mulberry"
    _DEFAULT_DESCRIPTION = "warm, natural, empathetic therapist voice"
    _DEFAULT_BASE_URL = (
        "https://api.rumik.ai"  # ponytail: deployment config; point at the eval sandbox
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key or settings.rumik_api_key
        self._base_url = base_url or self._DEFAULT_BASE_URL
        self._transport = transport or httpx.AsyncClient()

    async def aclose(self) -> None:
        """Close the owned transport (no-op for injected ones owned elsewhere)."""
        await self._transport.aclose()

    def _description(self, prosody: dict | None) -> str:
        if not prosody:
            return self._DEFAULT_DESCRIPTION
        return str(
            prosody.get("description") or prosody.get("directive") or self._DEFAULT_DESCRIPTION
        )

    async def synthesize(self, text: str, prosody: dict | None = None) -> AsyncIterator[bytes]:
        payload = {
            "model": self._model,
            "text": romanized_to_devanagari(text),
            "description": self._description(prosody),
        }
        try:
            response = await self._transport.post(
                f"{self._base_url}/v1/text-to-speech",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk
        except Exception:
            logger.exception("Rumik Silk TTS failed; yielding no audio")
            return


class RumikMulberryTTS(_RumikSilkTTS):
    """Mulberry: description-driven, 12 named speakers, Devanagari Hindi (§8.3)."""

    _model = "mulberry"


class RumikMugaTTS(_RumikSilkTTS):
    """Muga: expressive sibling — tone tags and inline events (§8.3, eval-time)."""

    _model = "muga"
