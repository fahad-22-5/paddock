"""Turn a CI report file into GitHub Actions annotations (shown on the run's page).

    python tools/ci_report.py report.txt
"""
import sys
from pathlib import Path


def escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "report.txt")
    text = path.read_text("utf-8", "replace") if path.exists() else "(no report was written)"
    lines = text.splitlines()
    failures = [l for l in lines if "FAIL" in l or "Error" in l or "error:" in l.lower()]
    if failures:
        print("::error title=Failures::" + escape("\n".join(failures[-40:])))
    # The end of the report (results, and the server log on failure). Annotations are
    # limited in size, so send the last part in a few chunks.
    tail = "\n".join(lines[-160:])
    chunks = [tail[i:i + 3500] for i in range(0, len(tail), 3500)][-4:]
    for n, chunk in enumerate(chunks, 1):
        print(f"::notice title=Report part {n}/{len(chunks)}::" + escape(chunk))


if __name__ == "__main__":
    main()
