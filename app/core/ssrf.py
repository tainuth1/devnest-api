import ipaddress
import logging
import socket
import urllib.parse
from typing import Any
import httpx

from app.core.config import settings

logger = logging.getLogger("app.security.ssrf")


class SSRFError(ValueError):
    """Raised when a URL fails SSRF safety checks."""
    pass


# Specific Cloud Metadata & Internal Networks
CLOUD_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS, GCP, Azure IMDS
    ipaddress.ip_address("169.254.169.250"),
    ipaddress.ip_address("169.254.169.251"),
    ipaddress.ip_address("169.254.169.253"),
}

# Carrier-Grade NAT (CGNAT) RFC 6598
CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")

# Localhost strings
LOCALHOST_STRINGS = {"localhost", "localhost.localdomain", "0.0.0.0"}


def parse_ip_address(ip_str: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """
    Parse a string or numeric value into an IPv4Address or IPv6Address.
    Handles standard IPv4/IPv6, integer, octal, hex, and IPv4-mapped IPv6 formats.
    Returns None if the string cannot be parsed as an IP.
    """
    ip_str = ip_str.strip().strip("[]")
    
    # Try standard ipaddress parsing
    try:
        ip = ipaddress.ip_address(ip_str)
        # Unwrap IPv4-mapped IPv6 address (e.g., ::ffff:127.0.0.1 -> 127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return ip.ipv4_mapped
        return ip
    except ValueError:
        pass

    # Try integer/octal/hex notation (e.g. 0x7f000001, 2130706433, 0177.0.0.1)
    try:
        if ip_str.startswith("0x") or ip_str.startswith("0X"):
            val = int(ip_str, 16)
            return ipaddress.IPv4Address(val)
        elif ip_str.isdigit():
            val = int(ip_str)
            return ipaddress.IPv4Address(val)
    except Exception:
        pass

    return None


def is_ip_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Determine if an IP address is internal, loopback, private, link-local, or reserved.
    """
    # If private IP blocking is disabled in settings, allow (except cloud metadata)
    if ip in CLOUD_METADATA_IPS:
        return True

    if not settings.SSRF_BLOCK_PRIVATE_IPS:
        return False

    # Check IPv4 or IPv6 properties
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True

    # Check Carrier-Grade NAT (CGNAT)
    if isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT_NETWORK:
        return True

    return False


def is_safe_url(url_string: str) -> tuple[bool, str]:
    """
    Validate whether a URL is safe against SSRF attacks.

    Checks:
    1. Scheme (only http and https allowed by default).
    2. Hostname presence and forbidden hostname strings (localhost, etc.).
    3. Allowlist validation (if SSRF_ALLOWLIST_DOMAINS is configured).
    4. IP parsing for raw IP hostnames.
    5. DNS resolution to ensure ALL resolved IPs are public and safe.

    Returns:
        (is_safe, error_reason)
    """
    if not url_string:
        return False, "URL string is empty"

    try:
        parsed = urllib.parse.urlparse(url_string)
    except Exception as exc:
        return False, f"Invalid URL format: {exc}"

    # 1. Scheme check
    scheme = (parsed.scheme or "").lower()
    allowed_schemes = [s.lower() for s in settings.SSRF_ALLOWED_SCHEMES]
    if scheme not in allowed_schemes:
        return False, f"Forbidden URL scheme '{parsed.scheme}'. Allowed: {allowed_schemes}"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing hostname"

    hostname_lower = hostname.lower()

    # 2. Localhost string check
    if hostname_lower in LOCALHOST_STRINGS:
        return False, f"Forbidden hostname '{hostname}'"

    # 3. Domain Allowlist check (if populated)
    if settings.SSRF_ALLOWLIST_DOMAINS:
        allowed = any(
            hostname_lower == domain.lower() or hostname_lower.endswith("." + domain.lower())
            for domain in settings.SSRF_ALLOWLIST_DOMAINS
        )
        if not allowed:
            return False, f"Domain '{hostname}' is not in SSRF allowlist"

    # 4. Check if hostname is directly an IP
    direct_ip = parse_ip_address(hostname)
    if direct_ip:
        if is_ip_forbidden(direct_ip):
            return False, f"Forbidden target IP address '{direct_ip}'"
        return True, ""

    # 5. DNS Resolution check
    port = parsed.port or (443 if scheme == "https" else 80)
    try:
        addr_info = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        return False, f"DNS resolution failed for hostname '{hostname}': {exc}"
    except Exception as exc:
        return False, f"Failed resolving hostname '{hostname}': {exc}"

    if not addr_info:
        return False, f"No IP addresses found for hostname '{hostname}'"

    # Check ALL resolved IP addresses
    resolved_ips = []
    for family, socktype, proto, canonname, sockaddr in addr_info:
        ip_str = sockaddr[0]
        ip_obj = parse_ip_address(ip_str)
        if not ip_obj:
            return False, f"Unparseable resolved IP address '{ip_str}'"

        resolved_ips.append(ip_obj)
        if is_ip_forbidden(ip_obj):
            logger.warning(
                "SSRF Protection triggered: Hostname '%s' resolved to forbidden IP '%s'",
                hostname,
                ip_obj,
            )
            return False, f"Hostname '{hostname}' resolved to forbidden IP '{ip_obj}'"

    return True, ""


def validate_safe_url(url_string: str) -> str:
    """
    Pydantic/FastAPI validation helper.
    Raises ValueError / SSRFError if URL is unsafe. Returns validated url_string.
    """
    is_safe, reason = is_safe_url(url_string)
    if not is_safe:
        raise SSRFError(f"SSRF Protection: {reason}")
    return url_string


async def safe_fetch(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: Any = None,
    timeout: float = 10.0,
    max_redirects: int | None = None,
) -> httpx.Response:
    """
    Safely execute an HTTP request with built-in SSRF protection and redirect validation.

    Prevents TOCTOU & DNS Rebinding attacks by re-verifying target URLs and redirects.
    """
    if max_redirects is None:
        max_redirects = settings.SSRF_MAX_REDIRECTS

    current_url = url
    current_method = method.upper()
    redirect_count = 0

    while True:
        # Validate target URL before making connection
        is_safe, reason = is_safe_url(current_url)
        if not is_safe:
            raise SSRFError(f"SSRF request blocked for '{current_url}': {reason}")

        # Send request with follow_redirects=False to control redirect safety
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.request(
                method=current_method,
                url=current_url,
                headers=headers,
                json=json,
                data=data,
            )

        # Check for HTTP redirect
        if response.is_redirect and "location" in response.headers:
            redirect_count += 1
            if redirect_count > max_redirects:
                raise SSRFError(f"Too many redirects ({redirect_count} > {max_redirects})")

            redirect_location = response.headers["location"]
            # Resolve relative redirect URLs against current_url
            next_url = urllib.parse.urljoin(current_url, redirect_location)
            
            logger.info("SSRF SafeFetch following redirect %d to: %s", redirect_count, next_url)
            current_url = next_url
            # GET on 301/302/303 redirect
            if response.status_code in (301, 302, 303):
                current_method = "GET"
                json = None
                data = None
        else:
            return response
