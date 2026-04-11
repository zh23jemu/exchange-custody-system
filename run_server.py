from __future__ import annotations

import argparse
import os

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动换汇资金托管系统")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="监听地址，默认 0.0.0.0")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8080")),
        help="监听端口，默认 8080",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=os.getenv("RELOAD", "false").lower() == "true",
        help="是否开启热更新",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
