"""Single deterministic net-name normalization implementation."""

from __future__ import annotations

import re
import unicodedata

from .models import NormalizeOptions


_REPLACEMENTS = str.maketrans({"-": "_", ".": "_", " ": "_", "/": "_"})
_CONTROL_CATEGORIES = {"Cc", "Cf"}


def normalize_net_name(net_name: str, options: NormalizeOptions | None = None) -> str:
    """Normalize one net name using the Rev C 9.5 algorithm.

    Steps: Unicode NFKC, reject control chars, uppercase, replace common
    separators with ``_``, collapse repeated underscores, strip underscores,
    optionally remove a leading plus sign.
    """

    options = options or NormalizeOptions()
    text = unicodedata.normalize("NFKC", str(net_name))
    bad = [ch for ch in text if unicodedata.category(ch) in _CONTROL_CATEGORIES]
    if bad:
        raise ValueError("Net name contains control/format characters")
    text = text.upper().translate(_REPLACEMENTS)
    text = re.sub(r"_+", "_", text).strip("_")
    if options.strip_leading_plus:
        text = text.lstrip("+")
    return text


def net_tokens(net_name: str) -> list[str]:
    return [token for token in normalize_net_name(net_name).split("_") if token]


def normalize_net_name_safe(net_name: str, options: NormalizeOptions | None = None) -> str:
    """Tolerant normalization for downstream consumers.

    Identical to normalize_net_name except control/format characters are
    stripped instead of raising. The strict variant remains the guessing
    engine's contract (a rejected name produces an explicit UNKNOWN
    fallback assignment); this variant lets exports, similarity
    suggestions, and revision matching keep working on such nets.
    """
    options = options or NormalizeOptions()
    text = unicodedata.normalize("NFKC", str(net_name))
    text = "".join(ch for ch in text if unicodedata.category(ch) not in _CONTROL_CATEGORIES)
    text = text.upper().translate(_REPLACEMENTS)
    text = re.sub(r"_+", "_", text).strip("_")
    if options.strip_leading_plus:
        text = text.lstrip("+")
    return text


def net_tokens_safe(net_name: str) -> list[str]:
    return [token for token in normalize_net_name_safe(net_name).split("_") if token]
