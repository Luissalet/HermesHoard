import argparse
import os
import uvicorn
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Hermes's Hoard")
    parser.add_argument("--port", type=int, default=int(os.environ.get("HERMES_PORT", "5221")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    uvicorn.run(create_app(port=args.port), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
