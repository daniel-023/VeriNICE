from __future__ import annotations


class EvidenceRetrievalError(RuntimeError):
    pass


class EvidenceRetrievalConfigurationError(EvidenceRetrievalError):
    pass


class EvidenceRetrievalProviderError(EvidenceRetrievalError):
    pass


class EvidenceRetrievalOutputError(EvidenceRetrievalError):
    pass
