"""Promo-owned validation for the configured phone purchase target."""

from __future__ import annotations

import ipaddress
from urllib.parse import unquote_to_bytes, urlsplit

import idna


_BROWSER_FORBIDDEN_HOST_CHARACTERS = frozenset("#/:<>?@[\\]^|")
_BROWSER_FORBIDDEN_DOMAIN_CHARACTERS = _BROWSER_FORBIDDEN_HOST_CHARACTERS | {
    "%"
}
_BROWSER_JOINERS = frozenset({"\u200c", "\u200d"})
_ASCII_DECIMAL_DIGITS = frozenset("0123456789")
_ASCII_HEXADECIMAL_DIGITS = frozenset("0123456789abcdefABCDEF")
_ASCII_OCTAL_DIGITS = frozenset("01234567")


class PhoneContinuationConfigurationError(ValueError):
    """The public phone boundary lacks a safe server-owned target."""


def validate_phone_purchase_url(value: str | None) -> str:
    """Return one absolute HTTPS server-owned target without credentials."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise PhoneContinuationConfigurationError(
            "PHONE_PURCHASE_URL must be an absolute HTTPS URL"
        )
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise PhoneContinuationConfigurationError(
            "PHONE_PURCHASE_URL must be an absolute HTTPS URL"
        ) from error
    canonical_hostname = (
        None
        if hostname is None
        else _canonical_browser_hostname(
            hostname=hostname,
            netloc=parsed.netloc,
            raw_authority=_raw_url_authority(value),
        )
    )
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or hostname is None
        or canonical_hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port == 0
    ):
        raise PhoneContinuationConfigurationError(
            "PHONE_PURCHASE_URL must be an absolute HTTPS URL"
        )
    return value


def _raw_url_authority(value: str) -> str:
    separator = value.find("://")
    if separator < 0:
        return ""
    start = separator + 3
    end = len(value)
    for delimiter in "/?#":
        position = value.find(delimiter, start)
        if position >= 0:
            end = min(end, position)
    return value[start:end]


def _raw_authority_host(authority: str) -> str:
    if authority.startswith("["):
        closing = authority.find("]")
        return authority if closing < 0 else authority[: closing + 1]
    if ":" in authority:
        return authority.rsplit(":", 1)[0]
    return authority


def _browser_invalid_host_character(character: str) -> bool:
    codepoint = ord(character)
    return codepoint <= 0x20 or 0x7F <= codepoint <= 0x9F


def _canonical_browser_hostname(
    *, hostname: str, netloc: str, raw_authority: str
) -> str | None:
    """Apply the browser special-URL host algorithm used by this boundary.

    UTS #46 mapping and contextual Bidi/joiner checks are shared through the
    installed IDNA implementation. Browser-relaxed label serialization stays
    here so URL-parser-compatible ASCII labels are not rejected by a stricter
    DNS-only validator.
    """

    raw_host = _raw_authority_host(raw_authority)
    if netloc.startswith("["):
        if not raw_host.startswith("[") or not raw_host.endswith("]"):
            return None
        if any(_browser_invalid_host_character(character) for character in raw_host):
            return None
        if "%" in raw_host:
            return None
        try:
            ipaddress.IPv6Address(hostname)
        except ValueError:
            return None
        return hostname

    if any(
        _browser_invalid_host_character(character)
        or character in _BROWSER_FORBIDDEN_HOST_CHARACTERS
        for character in raw_host
    ):
        return None
    try:
        decoded_host = unquote_to_bytes(raw_host).decode("utf-8")
        if any(
            _browser_invalid_host_character(character)
            or character in _BROWSER_FORBIDDEN_DOMAIN_CHARACTERS
            for character in decoded_host
        ):
            return None
        mapped_host = idna.uts46_remap(
            decoded_host,
            std3_rules=False,
            transitional=False,
        )
    except (UnicodeDecodeError, idna.IDNAError):
        return None
    if not mapped_host:
        return None

    ascii_labels: list[str] = []
    for label in mapped_host.split("."):
        if not label:
            ascii_labels.append("")
            continue
        try:
            idna.check_initial_combiner(label)
            idna.check_bidi(label)
            for position, character in enumerate(label):
                if character in _BROWSER_JOINERS and not idna.valid_contextj(
                    label, position
                ):
                    return None
            if label.isascii():
                ascii_label = label
            else:
                ascii_label = "xn--" + label.encode("punycode").decode("ascii")
        except (UnicodeError, idna.IDNAError):
            return None
        ascii_labels.append(ascii_label)

    canonical_host = ".".join(ascii_labels).casefold()
    if not canonical_host or _browser_ipv4_hostname_is_invalid(canonical_host):
        return None
    return canonical_host


def _browser_ipv4_hostname_is_invalid(hostname: str) -> bool:
    parts = hostname.split(".")
    if parts[-1] == "":
        parts.pop()
    if not parts:
        return False
    last = parts[-1]
    ends_in_number = (
        bool(last)
        and all(character in _ASCII_DECIMAL_DIGITS for character in last)
    ) or _parse_browser_ipv4_number(last) is not None
    if not ends_in_number:
        return False
    if len(parts) > 4:
        return True
    numbers = [_parse_browser_ipv4_number(part) for part in parts]
    if any(number is None for number in numbers):
        return True
    parsed_numbers = [number for number in numbers if number is not None]
    return any(number > 255 for number in parsed_numbers[:-1]) or (
        parsed_numbers[-1] >= 256 ** (5 - len(parsed_numbers))
    )


def _parse_browser_ipv4_number(value: str) -> int | None:
    if not value:
        return None
    radix = 10
    digits = value
    allowed_digits = _ASCII_DECIMAL_DIGITS
    if value[:2].casefold() == "0x":
        radix = 16
        digits = value[2:]
        allowed_digits = _ASCII_HEXADECIMAL_DIGITS
    elif len(value) >= 2 and value.startswith("0"):
        radix = 8
        digits = value[1:]
        allowed_digits = _ASCII_OCTAL_DIGITS
    if not digits:
        return 0
    if any(character not in allowed_digits for character in digits):
        return None
    return int(digits, radix)


__all__ = ["PhoneContinuationConfigurationError", "validate_phone_purchase_url"]
