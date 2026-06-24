"""5sim.net provider — register into unified registry."""
from core.base_sms import (  # noqa: F401 – re-exports
    FIVESIM_DEFAULT_COUNTRY,
    FIVESIM_DEFAULT_PRODUCT,
    FiveSimProvider,
)
from providers.registry import register_provider

register_provider("sms", "fivesim_api")(FiveSimProvider)
