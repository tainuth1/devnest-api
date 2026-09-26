#!/usr/bin/env python3
"""
Test script for OWASP A08 Software and Data Integrity Failures defenses.
"""

import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.integrity import (
    generate_data_signature,
    verify_data_signature,
    sign_payload,
    verify_signed_payload,
    IntegrityError,
)


def test_integrity_features():
    print("[+] Testing OWASP A08 Data Integrity Features...")

    # 1. HMAC Signature Verification
    data = "critical_user_action_12345"
    sig = generate_data_signature(data)
    assert verify_data_signature(data, sig), "Valid HMAC signature failed verification"
    assert not verify_data_signature(data + "_tampered", sig), "Tampered data accepted HMAC signature"
    print("  [✓] HMAC signature generation and constant-time verification working")

    # 2. Signed Payload Serialization & Verification
    original_payload = {"user_id": "usr_99", "role": "admin", "action": "upgrade"}
    signed_token = sign_payload(original_payload, ttl_seconds=60)
    decoded_payload = verify_signed_payload(signed_token)
    assert decoded_payload == original_payload, "Decoded payload does not match original"
    print("  [✓] Signed payload token creation and verification successful")

    # 3. Tampered Signed Payload Rejection
    tampered_token = signed_token[:-4] + "AAAA"
    try:
        verify_signed_payload(tampered_token)
        assert False, "Tampered signed payload should have failed verification"
    except IntegrityError as e:
        print(f"  [✓] Tampered signed payload rejected: {e}")

    # 4. Expired Signed Payload Rejection
    expired_token = sign_payload(original_payload, ttl_seconds=-10)
    try:
        verify_signed_payload(expired_token)
        assert False, "Expired signed payload should have failed verification"
    except IntegrityError as e:
        print(f"  [✓] Expired signed payload rejected: {e}")

    print("\n[✓] All OWASP A08 Data Integrity Tests Passed!")


if __name__ == "__main__":
    test_integrity_features()
