from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automusic.config import load_dotenv
from automusic.web_app import create_app, create_default_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local AutoMusic web wizard")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("외부 네트워크 공개는 지원하지 않습니다.")
    return args


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    load_dotenv(root / ".env")
    app = create_app(create_default_service(root))
    host = "127.0.0.1" if args.host == "localhost" else args.host
    app.run(host=host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
