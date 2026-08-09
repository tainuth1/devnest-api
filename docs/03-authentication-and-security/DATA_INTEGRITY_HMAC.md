# Data Integrity & HMAC Payload Signing

This document details the Software and Data Integrity safeguards (`app/core/integrity.py`) implemented for OWASP A08 (Software and Data Integrity Failures), including HMAC-SHA256 payload signing, constant-time verification, and replay attack prevention.

---

## Data Integrity Architecture

The data integrity module protects critical payload data (such as webhooks, state tokens, or exported sensitive records) against unauthorized tampering, forgery, or replay attacks.

```text
[Plain Payload Dict] ──► [Canonical JSON Serialization] ──► [HMAC-SHA256 Signing]
                                                                     │
                                                                     ▼
[URL-Safe Base64 Token] ◄── [Package Container: body + sig] ◄────────┘
```

---

## 1. HMAC SHA-256 Payload Signing (`generate_data_signature`)

Signatures are computed using the SHA-256 hash algorithm keyed with the application's 64-character (≥ 512-bit) `SECRET_KEY`.

```python
def generate_data_signature(data: str | bytes) -> str:
    """
    Generate an HMAC-SHA256 signature for data using the application SECRET_KEY.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    secret = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(secret, data, hashlib.sha256).hexdigest()
```

### Tamper-Evident Token Generation (`sign_payload`)

To package a dictionary payload into a signed, tamper-evident token string:

```python
token = sign_payload(payload={"action": "export", "user_id": "123"}, ttl_seconds=3600)
```

1. **Timestamp Binding**: Automatically attaches issued-at (`iat`) and expiration (`exp`) epoch timestamps.
2. **Canonical Serialization**: Serializes data to JSON with key sorting (`sort_keys=True`) and compact separators (`separators=(",", ":")`) to guarantee identical byte representations regardless of key insertion order.
3. **HMAC Calculation**: Computes the SHA-256 signature over the canonical JSON string.
4. **Base64 Encoding**: Packages the raw body string and signature into a JSON container encoded as URL-safe Base64.

---

## 2. Constant-Time Signature Verification (`verify_data_signature`)

To prevent timing-side-channel attacks where an attacker deduces signature bytes by measuring comparison latency, verification uses Python's built-in `hmac.compare_digest`.

```python
def verify_data_signature(data: str | bytes, signature: str) -> bool:
    """
    Constant-time HMAC-SHA256 signature verification to prevent timing attacks.
    """
    expected = generate_data_signature(data)
    return hmac.compare_digest(expected, signature)
```

### Standard `==` vs. `hmac.compare_digest`

| Comparison Method         | Execution Character                                                         | Security Risk                                                                          |
| :------------------------ | :-------------------------------------------------------------------------- | :------------------------------------------------------------------------------------- |
| **Standard String `==`**  | Short-circuiting (returns `False` on first non-matching byte)               | Vulnerable to microsecond timing measurements allowing byte-by-byte signature forgery. |
| **`hmac.compare_digest`** | Constant-time execution (compares all bytes regardless of early mismatches) | Immune to timing-side-channel attacks.                                                 |

---

## 3. Replay Attack Protection & Expiration Validation

`verify_signed_payload(token)` decodes signed tokens and enforces payload validity and freshness.

```python
def verify_signed_payload(token: str) -> dict[str, Any]:
    ...
```

### Validation Sequence

1. **Base64 Decoding & Unpackaging**: Decodes the URL-safe Base64 string and unpacks `body` and `sig`.
2. **Signature Verification**: Verifies `verify_data_signature(raw_body, provided_sig)`. If the signature does not match expected output:
    - An `INTEGRITY_CHECK_FAILED` security audit alert is logged to database audit logs.
    - An `IntegrityError` exception is raised.
3. **Expiration & Replay Check**: Compares `now = int(tz.now().timestamp())` against `exp`. If `now >= exp`, the token is rejected with `IntegrityError("Token has expired")`.

### Exception Handling & Audit Logging

When signature tampering is detected, an alert is logged for security monitoring:

```python
audit_logger.log_event(
    event_type=AuditEventType.INTEGRITY_CHECK_FAILED,
    status=AuditStatus.ALERT,
    details={"reason": "HMAC signature mismatch — possible tampering detected"},
)
```
