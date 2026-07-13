"""Deterministic numeric voltage token parser."""

from __future__ import annotations

import re

import unicodedata

from .models import VoltageToken

# Match tokens that explicitly include a V marker: 3V3, 12V, +15V, M12V, P3V3.
_V_TOKEN_RE = re.compile(r"(?<![A-Z0-9])(?P<prefix>[+\-]|P|M|N)?(?P<num>\d+V\d*|\d+V)(?![A-Z0-9])")
# Conservative high-voltage shorthand accepted by the requirements: HV400.
_HV_SHORTHAND_RE = re.compile(r"(?<![A-Z0-9])HV(?P<num>\d{2,4})(?![A-Z0-9])")


def _token_to_float(token: str) -> float:
    token = token.upper()
    if "V" not in token:
        return float(token)
    before, after = token.split("V", 1)
    if after == "":
        return float(before)
    return float(f"{int(before)}.{after}")


def parse_voltage_token(net_name: str) -> VoltageToken | None:
    """Return the first explicit voltage token, avoiding index numbers.

    Digits in GPIO12, ADC_IN1, UART2_TX, CH4, M2_CS and N1 are not voltage
    values because they are not attached to an explicit V marker. HV400 is
    accepted as a special high-voltage shorthand requested by the spec.
    """

    text = unicodedata.normalize("NFKC", str(net_name)).upper()
    text = text.replace(".", "_").replace(" ", "_").replace("/", "_")
    text = re.sub(r"_+", "_", text).strip("_")
    match = _V_TOKEN_RE.search(text)
    if match:
        prefix = match.group("prefix") or ""
        raw_num = match.group("num")
        polarity = -1 if prefix in {"-", "M", "N"} else 1
        marker = prefix or "V"
        return VoltageToken(
            raw_token=match.group(0),
            voltage_v=polarity * _token_to_float(raw_num),
            polarity=polarity,
            marker=marker,
            start=match.start(),
            end=match.end(),
        )
    match = _HV_SHORTHAND_RE.search(text)
    if match:
        raw_num = match.group("num")
        return VoltageToken(
            raw_token=match.group(0),
            voltage_v=float(raw_num),
            polarity=1,
            marker="HV",
            start=match.start(),
            end=match.end(),
        )
    return None
