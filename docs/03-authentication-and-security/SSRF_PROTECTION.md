# Server-Side Request Forgery (SSRF) Protection

This document details the Server-Side Request Forgery (SSRF) validation engine, IP blocklists, DNS resolution checks, and safe HTTP fetch mechanisms implemented in `app/core/ssrf.py` for OWASP A10 (Server-Side Request Forgery).

---

## SSRF Validation Architecture

The SSRF validation module ensures that any outbound HTTP request triggered by the application cannot target internal microservices, cloud metadata APIs, loopback interfaces, or private infrastructure networks.

```text
[Outbound URL Request]
       │
       ▼
┌─────────────────────────────────────────┐
│ 1. Scheme Validation                    │  Allow http/https only
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 2. Localhost & Domain Allowlist Check   │  Block localhost strings & enforce domain rules
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 3. Direct IP Parsing                    │  Parse IPv4/v6, octal, hex, IPv4-mapped IPv6
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 4. DNS Resolution & All-IP Inspection   │  Resolve DNS & block if ANY IP is forbidden
└─────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ 5. Redirect Re-validation (safe_fetch) │  Re-verify target IP on HTTP 3xx redirects
└─────────────────────────────────────────┘
```

---

## 1. Outbound URL Parsing & IP Validation (`app/core/ssrf.py`)

URL verification is performed by `is_safe_url(url_string)`.

```python
def is_safe_url(url_string: str) -> tuple[bool, str]:
    ...
```

### Validation Steps

1. **Protocol Scheme Filtering**: Verifies `url.scheme` against `settings.SSRF_ALLOWED_SCHEMES` (default: `["http", "https"]`). Rejects non-HTTP schemes like `file://`, `gopher://`, `ftp://`, or `dict://`.
2. **Localhost String Filtering**: Rejects hostnames explicitly listed in `LOCALHOST_STRINGS` (`"localhost"`, `"localhost.localdomain"`, `"0.0.0.0"`).
3. **Domain Allowlist Validation**: If `settings.SSRF_ALLOWLIST_DOMAINS` is populated, enforces that the hostname matches an explicit domain allowlist or its subdomains.
4. **Direct IP Parsing (`parse_ip_address`)**: Handles non-standard IP representations used by attackers to bypass naïve string checks:
    - Standard IPv4/IPv6 addresses (`127.0.0.1`, `::1`).
    - Hexadecimal IP formats (e.g. `0x7f000001` -> `127.0.0.1`).
    - Decimal integer IP formats (e.g. `2130706433` -> `127.0.0.1`).
    - IPv4-mapped IPv6 addresses (e.g. `::ffff:127.0.0.1` -> `127.0.0.1`).
5. **DNS Resolution & Multi-A Record Inspection**: Performs synchronous socket resolution (`socket.getaddrinfo`). If **ANY** resolved IP address matches a forbidden IP range, the URL is rejected.

---

## 2. Forbidden IP & Network Blocklists

IP safety is evaluated by `is_ip_forbidden(ip)`.

### Blocked Network Ranges

| Network Category              | IP Range / Subnet                                   | Security Rationale                                                                |
| :---------------------------- | :-------------------------------------------------- | :-------------------------------------------------------------------------------- |
| **Cloud Metadata Services**   | `169.254.169.254`, `169.254.169.250-253`            | AWS/GCP/Azure Instance Metadata Service (IMDSv1/IMDSv2) exposing IAM credentials. |
| **RFC 1918 Private Networks** | `10.0.0.0/8`<br>`172.16.0.0/12`<br>`192.168.0.0/16` | Internal organization network ranges and VPC infrastructure.                      |
| **Loopback Addresses**        | `127.0.0.0/8`, `::1/128`                            | Localhost services running on internal ports (Redis, Postgres, Docker daemons).   |
| **Link-Local Addresses**      | `169.254.0.0/16`, `fe80::/10`                       | Auto-configured local link networks.                                              |
| **Carrier-Grade NAT (CGNAT)** | `100.64.0.0/10` (RFC 6598)                          | Shared address space used by internal cloud gateways and service meshes.          |
| **Reserved / Multicast**      | `0.0.0.0/8`, `224.0.0.0/4`, `240.0.0.0/4`           | Unspecified, multicast, and reserved experimental ranges.                         |

---

## 3. Safe Outbound HTTP Client (`safe_fetch`)

To execute outbound HTTP requests securely without exposing the server to Time-of-Check to Time-of-Use (TOCTOU) or DNS Rebinding redirect attacks, use `safe_fetch(...)`.

```python
response = await safe_fetch(
    url="https://api.external.com/data",
    method="GET",
    timeout=5.0,
)
```

### Prevention of TOCTOU & Redirect SSRF Attacks

1. **Disabled Auto-Redirects (`follow_redirects=False`)**: Standard HTTP clients automatically follow `301`/`302` redirects. Attackers often supply a safe initial URL (e.g. `https://example.com`) that issues a redirect to `http://169.254.169.254/latest/meta-data/`.
2. **Redirect Loop Guard**: Enforces a maximum redirect depth via `settings.SSRF_MAX_REDIRECTS` (default: 3).
3. **Location Re-validation**: Every HTTP `3xx` `Location` response header is re-parsed and re-validated using `is_safe_url(...)` before establishing a new connection. If the target location redirects to an internal IP, an `SSRFError` is raised immediately.
