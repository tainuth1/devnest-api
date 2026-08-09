import sys
import subprocess
from pathlib import Path


def run_audit(requirements_path: Path) -> int:
    """Run pip-audit against the specified requirements file."""
    if not requirements_path.exists():
        print(f"Error: Requirements file not found at {requirements_path}")
        return 1

    print(f"[+] Auditing dependencies in {requirements_path} for known vulnerabilities...")
    
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "-r",
        str(requirements_path),
        "--format",
        "columns",
        "--strict",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            print("Audit Passed: No known vulnerable components found.")
        else:
            print("Audit Failed: Known vulnerabilities detected!")
        
        return result.returncode
    except FileNotFoundError:
        print("Error: pip-audit tool not installed. Run `pip install pip-audit` first.")
        return 1


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    req_file = project_root / "requirements.txt"
    sys.exit(run_audit(req_file))
