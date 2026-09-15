from __future__ import annotations


class ProviderError(RuntimeError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderQuotaError(ProviderRateLimitError):
    pass


class ProviderConfigurationError(ProviderError):
    pass

