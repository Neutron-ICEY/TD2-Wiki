"""Offline publishing contracts; no login, network, or production writes."""
import unicodedata


class PublishError(ValueError):
    """Controlled diagnostic that never embeds source content or secret values."""


def require(condition, message):
    if not condition:
        raise PublishError(message)


def normalized_title_name(name):
    """Shared conservative collision key; live normalization still needs preflight."""
    return " ".join(unicodedata.normalize('NFC', name).replace('_', ' ').split()).casefold()
