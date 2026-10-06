"""Official provider API boundaries for Messenger.

No credentials or unofficial web/session automation belong in the domain layer.
Deployments may inject adapters backed by each provider's official API after
separately provisioning credentials in a secret manager.
"""
from typing import Protocol


class MessengerAdapter(Protocol):
    provider: str

    def list_updates(self, cursor: str | None = None) -> tuple[list[dict], str | None]: ...
    def send_message(self, conversation_ref: str, text: str) -> dict: ...


class TelegramOfficialAdapter:
    """Adapter contract marker. Configure only with an official Telegram API client."""
    provider = 'telegram'


class MaxOfficialAdapter:
    """Adapter contract marker. Configure only with an official MAX API client."""
    provider = 'max'


def adapter_for(provider: str, configured: dict[str, MessengerAdapter] | None = None):
    if provider not in {'telegram', 'max'}:
        raise ValueError('Поддерживаются только Telegram и MAX')
    return (configured or {}).get(provider)
