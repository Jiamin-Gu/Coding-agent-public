"""Request GET /health and verify the JSON response. Standard library only."""

import json
import sys
import urllib.request

URL = "http://127.0.0.1:8765/health"


def main():
    with urllib.request.urlopen(URL, timeout=5) as resp:
        status = resp.status
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    print("status:", status)
    print("body:", data)
    ok = status == 200 and data == {"ok": True}
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
