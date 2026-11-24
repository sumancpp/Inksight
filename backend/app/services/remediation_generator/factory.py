from typing import Optional
from app.core.config import settings
from app.services.remediation_generator.base import BaseRemediationGenerator
from app.services.remediation_generator.mock_generator import MockRemediationGenerator


def get_remediation_generator(provider_name: Optional[str] = None) -> BaseRemediationGenerator:
    """
    Factory function returning the configured remediation generator instance.
    Defaults to settings.REMEDIATION_PROVIDER.
    """
    provider = (provider_name or settings.REMEDIATION_PROVIDER).lower()
    if provider == "mock":
        return MockRemediationGenerator()
    else:
        raise ValueError(
            f"Unsupported remediation generator provider: '{provider}'. "
            "Supported providers: ['mock']."
        )
