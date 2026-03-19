"""Exceptions for the certified carbon receipts system."""


class EnterpriseFeatureNotAvailableError(Exception):
    """Raised when an enterprise feature is attempted without required dependencies installed."""

    pass


class SigningError(Exception):
    """Raised when cryptographic signing or verification fails."""

    pass


class PDFGenerationError(Exception):
    """Raised when PDF generation fails."""

    pass
