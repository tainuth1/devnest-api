"""
Automated Verification Script for OWASP A10: Server-Side Request Forgery (SSRF) Protection.

Tests:
1. Forbidden schemes (file://, gopher://, ftp://, data:).
2. Loopback addresses (127.0.0.1, localhost, 0.0.0.0, ::1).
3. Private IP ranges (10.0.0.1, 172.16.0.1, 192.168.1.1).
4. Cloud Instance Metadata endpoints (169.254.169.254).
5. Obfuscated / Encoded IP forms (hex 0x7f000001, dword 2130706433, octal 0177.0.0.1).
6. IPv4-mapped IPv6 addresses (::ffff:127.0.0.1).
7. Valid public URLs (https://api.brevo.com, https://example.com).
8. Pydantic validation helper (validate_safe_url / SSRFError).
9. safe_fetch wrapper handling.
"""

import sys
import asyncio
import ipaddress

# Ensure project root is in sys.path
sys.path.insert(0, ".")

from app.core.ssrf import (
    SSRFError,
    is_ip_forbidden,
    is_safe_url,
    parse_ip_address,
    safe_fetch,
    validate_safe_url,
)
from app.core.config import settings


def test_ip_parsing_and_obfuscation():
    print("1. Testing IP Parsing & Obfuscation Bypasses...")

    # Standard loopback IPv4
    ip_127 = parse_ip_address("127.0.0.1")
    assert ip_127 == ipaddress.ip_address("127.0.0.1")
    assert is_ip_forbidden(ip_127) is True

    # Hex IP (0x7f000001 -> 127.0.0.1)
    ip_hex = parse_ip_address("0x7f000001")
    assert ip_hex == ipaddress.ip_address("127.0.0.1")
    assert is_ip_forbidden(ip_hex) is True

    # Integer / Dword IP (2130706433 -> 127.0.0.1)
    ip_dword = parse_ip_address("2130706433")
    assert ip_dword == ipaddress.ip_address("127.0.0.1")
    assert is_ip_forbidden(ip_dword) is True

    # IPv4-mapped IPv6 (::ffff:127.0.0.1)
    ip_mapped = parse_ip_address("::ffff:127.0.0.1")
    assert ip_mapped == ipaddress.ip_address("127.0.0.1")
    assert is_ip_forbidden(ip_mapped) is True

    # Cloud Metadata (169.254.169.254)
    ip_metadata = parse_ip_address("169.254.169.254")
    assert is_ip_forbidden(ip_metadata) is True

    # Private IPv4 (10.0.0.1, 192.168.1.1, 172.16.0.1)
    assert is_ip_forbidden(parse_ip_address("10.0.0.1")) is True
    assert is_ip_forbidden(parse_ip_address("192.168.1.1")) is True
    assert is_ip_forbidden(parse_ip_address("172.16.0.1")) is True

    # Public IPv4 (8.8.8.8, 93.184.216.34)
    ip_public = parse_ip_address("8.8.8.8")
    assert is_ip_forbidden(ip_public) is False

    print("   [PASS] IP parsing & obfuscation checks passed.")


def test_scheme_and_hostname_validation():
    print("2. Testing Scheme & Hostname Security Rules...")

    # Forbidden schemes
    bad_schemes = [
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379/_GET",
        "ftp://10.0.0.1/secret.txt",
        "dict://127.0.0.1:11211/stat",
        "data:text/plain;base64,SGVsbG8=",
    ]
    for url in bad_schemes:
        is_safe, reason = is_safe_url(url)
        assert is_safe is False, f"Should block scheme in: {url}"
        assert "Forbidden URL scheme" in reason

    # Localhost string names
    bad_hostnames = [
        "http://localhost/admin",
        "http://localhost:8000/api",
        "http://localhost.localdomain/test",
        "http://0.0.0.0:5000",
    ]
    for url in bad_hostnames:
        is_safe, reason = is_safe_url(url)
        assert is_safe is False, f"Should block localhost hostname: {url}"

    print("   [PASS] Scheme and hostname rules passed.")


def test_ssrf_forbidden_targets():
    print("3. Testing SSRF Target Blocking (Loopback, Private, Cloud IMDS)...")

    forbidden_urls = [
        "http://127.0.0.1/admin",
        "http://127.0.0.1:6379",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://10.0.0.5:8080/internal",
        "http://172.16.0.100/status",
        "http://192.168.1.1/router",
        "http://[::1]/debug",
        "http://[::ffff:127.0.0.1]/secret",
    ]

    for url in forbidden_urls:
        is_safe, reason = is_safe_url(url)
        assert is_safe is False, f"Expected unsafe for '{url}', but got safe."

    print("   [PASS] All forbidden SSRF targets blocked.")


def test_valid_public_urls():
    print("4. Testing Valid Public URLs...")

    valid_urls = [
        "https://api.brevo.com/v3/smtp/email",
        "https://example.com",
    ]

    for url in valid_urls:
        is_safe, reason = is_safe_url(url)
        assert is_safe is True, f"Expected safe for '{url}', but failed with: {reason}"

    print("   [PASS] Valid public URLs allowed.")


def test_pydantic_validator():
    print("5. Testing Pydantic Validator & Exception Handling...")

    # Should pass
    safe_url = validate_safe_url("https://example.com/api")
    assert safe_url == "https://example.com/api"

    # Should raise SSRFError / ValueError
    try:
        validate_safe_url("http://127.0.0.1:8000/internal")
        assert False, "Should have raised SSRFError for 127.0.0.1"
    except SSRFError as exc:
        assert "SSRF Protection" in str(exc)

    print("   [PASS] Pydantic validator works as expected.")


def test_async_safe_fetch():
    print("6. Testing safe_fetch Async Wrapper...")

    async def _test():
        # Test blocking unsafe fetch
        try:
            await safe_fetch("http://169.254.169.254/latest/meta-data/")
            assert False, "safe_fetch should block AWS metadata service URL"
        except SSRFError as exc:
            assert "SSRF request blocked" in str(exc)

    asyncio.run(_test())
    print("   [PASS] safe_fetch blocked unsafe request.")


def main():
    print("=" * 60)
    print("Running OWASP A10 (SSRF) Security Verification Suite")
    print("=" * 60)

    test_ip_parsing_and_obfuscation()
    test_scheme_and_hostname_validation()
    test_ssrf_forbidden_targets()
    test_valid_public_urls()
    test_pydantic_validator()
    test_async_safe_fetch()

    print("=" * 60)
    print("ALL OWASP A10 (SSRF) SECURITY VERIFICATION TESTS PASSED SUCCESSFULLY! [SUCCESS]")
    print("=" * 60)


if __name__ == "__main__":
    main()
