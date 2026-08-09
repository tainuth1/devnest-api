#!/usr/bin/env python3
"""
Test script for OWASP A07 Identification and Authentication Failures defenses.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.password_security import validate_password_strength


def test_password_validation():
    print("[+] Testing OWASP A07 Password Security Rules...")

    # 1. Valid password
    valid_pwd = "SuperSecurePassword123!"
    res = validate_password_strength(valid_pwd, username="john_doe", email="john@example.com")
    assert res == valid_pwd, "Valid password failed validation"
    print("  [✓] Strong valid password accepted")

    # 2. Too short
    try:
        validate_password_strength("Short1!")
        assert False, "Should have failed short password check"
    except ValueError as e:
        print(f"  [✓] Short password rejected: {e}")

    # 3. Missing uppercase/lowercase/digit/special
    try:
        validate_password_strength("alllowercase123!")
        assert False, "Should have failed uppercase check"
    except ValueError as e:
        print(f"  [✓] Missing uppercase rejected: {e}")

    # 4. Common breached password
    try:
        validate_password_strength("Password123!", username="john_doe", email="john@example.com")
        assert False, "Should have failed breached password check"
    except ValueError as e:
        print(f"  [✓] Common breached password 'Password123!' rejected: {e}")

    # 5. Contains username
    try:
        validate_password_strength("MyJohn_doePass1!", username="john_doe", email="john@example.com")
        assert False, "Should have failed username context check"
    except ValueError as e:
        print(f"  [✓] Password containing username rejected: {e}")

    # 6. Contains email
    try:
        validate_password_strength("MyJohnPass123!", username="johndoe", email="john@example.com")
        assert False, "Should have failed email context check"
    except ValueError as e:
        print(f"  [✓] Password containing email prefix rejected: {e}")

    print("\n[✓] All OWASP A07 Password Security Tests Passed!")


if __name__ == "__main__":
    test_password_validation()
