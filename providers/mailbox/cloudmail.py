"""CloudMail / SkyMail — register into unified registry."""
from core.base_mailbox import SkyMailMailbox  # noqa: F401
from providers.registry import register_provider

register_provider("mailbox", "cloudmail_api")(SkyMailMailbox)
