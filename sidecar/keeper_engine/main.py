"""本地推理服务启动入口。

启动：mise run sidecar [-- --port 8761]
"""

from __future__ import annotations

import argparse

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Keeper 本地推理服务")
    parser.add_argument("--host", default=None, help="仅本地，勿绑 0.0.0.0（默认取配置）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认取配置）")
    args = parser.parse_args()

    app = create_app()
    settings = app.container.settings()

    import uvicorn

    uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)


if __name__ == "__main__":
    main()
