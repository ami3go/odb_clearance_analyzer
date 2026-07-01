"""Layer-role heuristics for IPC-style internal/external clearance estimates."""

from __future__ import annotations

import re


_EXTERNAL_EXACT = {
    "top", "bottom", "bot", "front", "back", "f.cu", "b.cu", "f_cu", "b_cu",
    "toplayer", "bottomlayer", "top_layer", "bottom_layer", "topcopper", "bottomcopper",
    "component", "componentlayer", "solder", "solderlayer",
}

_EXTERNAL_TOKENS = (
    "top",
    "bottom",
    "bot",
    "front",
    "back",
    "outer",
    "external",
)

_INTERNAL_TOKENS = (
    "inner",
    "internal",
    "inlayer",
    "mid",
    "plane",
    "prep",
)


def normalize_layer_role(role: str | None) -> str:
    """Return either ``external`` or ``internal``."""

    text = (role or "").strip().lower()
    if text in {"int", "inner", "internal", "inside"}:
        return "internal"
    if text in {"ext", "outer", "external", "outside", "top", "bottom"}:
        return "external"
    return "external"


def _compact(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def guess_layer_roles(layers: list[str]) -> dict[str, str]:
    """Guess each signal layer as external/internal from common PCB naming patterns.

    The result is only a default; the GUI lets the user override each layer.
    """

    return {layer: guess_layer_role(layer, index=i, total=len(layers))[0] for i, layer in enumerate(layers)}


def guess_layer_role(layer_name: str, index: int, total: int) -> tuple[str, str]:
    """Return ``(role, reason)`` for one layer."""

    name = layer_name.strip()
    lower = name.lower().strip()
    compact = _compact(name)

    # Direct/common external names.
    if lower in _EXTERNAL_EXACT or compact in _EXTERNAL_EXACT:
        return "external", "common external layer name"

    # Common KiCad/ODB names.
    if lower in {"f.cu", "front.cu", "top.cu"}:
        return "external", "front/top copper naming"
    if lower in {"b.cu", "back.cu", "bottom.cu"}:
        return "external", "back/bottom copper naming"

    # InnerN / InN / Internal naming.
    if re.match(r"^(inner|internal|in)[_\-\s\.]?\d+$", lower) or compact.startswith("inner"):
        return "internal", "inner/internal layer naming"
    if lower.startswith("inner") or lower.startswith("internal"):
        return "internal", "inner/internal layer naming"

    if any(token in compact for token in _EXTERNAL_TOKENS):
        return "external", "external/top/bottom keyword"
    if any(token in compact for token in _INTERNAL_TOKENS):
        # Do not override obvious first/last layer unless name explicitly says inner/internal.
        if index not in (0, max(0, total - 1)) or compact.startswith(("inner", "internal", "in")):
            return "internal", "internal/plane keyword"

    # signal1/signal2/... or l1/l2/layer1 style stacks: first/last are external.
    numeric_match = re.match(r"^(signal|sig|layer|l)(\d+)$", compact)
    if numeric_match and total > 1:
        if index == 0:
            return "external", "first numbered/signal layer"
        if index == total - 1:
            return "external", "last numbered/signal layer"
        return "internal", "middle numbered/signal layer"

    # Fallback by stack order. This is only a default; user can change it.
    if total <= 2:
        return "external", "two-layer/default external"
    if index == 0:
        return "external", "first layer fallback"
    if index == total - 1:
        return "external", "last layer fallback"
    return "internal", "middle layer fallback"


def role_display(role: str | None) -> str:
    """Return display text for layer-role values."""

    return "internal" if normalize_layer_role(role) == "internal" else "external"
