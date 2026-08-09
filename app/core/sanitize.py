"""
Input sanitization utilities for preventing injection attacks.

OWASP A03: Injection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This module provides helpers to strip or neutralize dangerous characters from
user-supplied strings before they are used in security-sensitive contexts:

  - Log injection: attackers embed \\n or \\r in user input to forge log entries.
  - Email header/content injection: \\n in recipient name or subject can
    inject extra MIME headers or body content.
  - Display injection: Unicode control characters (null bytes, RTL override,
    zero-width spaces) can spoof UI rendering.

Design decisions
━━━━━━━━━━━━━━━━
- We prefer stripping over rejecting so that legitimate requests from users
  with unusual (but real) names are not silently dropped.
- The sanitized value is used ONLY for log messages and email payloads.
  The original validated value is what gets stored in the database.
"""

import re
import unicodedata


# ASCII control characters: 0x00–0x1F and DEL (0x7F)
_ASCII_CONTROL_RE = re.compile(r"[\x00-\x1F\x7F]")

# Unicode categories whose characters are invisible / directional overrides:
#   Cc = Other, control  (covers ASCII controls above)
#   Cf = Other, format   (zero-width space, RTL/LTR marks, soft hyphen, etc.)
_UNSAFE_UNICODE_CATEGORIES = {"Cc", "Cf"}


def sanitize_for_log(value: str, replacement: str = " ") -> str:
    """
    Return a copy of *value* safe for embedding in log messages.

    Replaces ASCII control characters (\\n, \\r, \\t, NUL, etc.) with
    *replacement* (default: a single space) so that an attacker cannot forge
    fake log entries by injecting newlines into user-supplied strings.

    Example
    -------
    >>> sanitize_for_log("alice\\nWARNING fake entry")
    'alice WARNING fake entry'
    """
    if not isinstance(value, str):
        value = str(value)
    return _ASCII_CONTROL_RE.sub(replacement, value)


def strip_control_characters(value: str) -> str:
    """
    Remove all ASCII and Unicode control / format characters from *value*.

    Removes characters in Unicode categories Cc (control) and Cf (format),
    which includes:
      - Null bytes (\\x00)
      - Newlines / carriage returns
      - Zero-width spaces (U+200B)
      - Right-to-left override (U+202E)
      - Soft hyphens, word joiners, etc.

    Unlike sanitize_for_log(), this function REMOVES (not replaces) the
    characters, making it suitable for name fields and email content where
    a substitution character would look odd.

    Example
    -------
    >>> strip_control_characters("John\\u0000 Doe\\u200b")
    'John Doe'
    """
    if not isinstance(value, str):
        value = str(value)
    return "".join(
        ch for ch in value
        if unicodedata.category(ch) not in _UNSAFE_UNICODE_CATEGORIES
    )


def sanitize_email_field(value: str) -> str:
    """
    Strip control characters from a user-supplied string before embedding
    it in an email subject, recipient name, or plain-text body.

    Prevents email header injection and MIME body manipulation attacks where
    an attacker supplies a username or subject containing \\n, \\r characters
    to inject extra headers or body sections.

    Example
    -------
    >>> sanitize_email_field("alice\\nBcc:attacker@evil.com")
    'aliceBcc:attacker@evil.com'
    """
    return strip_control_characters(value)
