"""Errors exposed by the claim decomposition service."""


class DecompositionError(RuntimeError):
    pass


class DecompositionConfigurationError(DecompositionError):
    pass


class DecompositionProviderError(DecompositionError):
    pass


class DecompositionOutputError(DecompositionError):
    pass
