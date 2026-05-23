"""游戏 HTTP API 入口（供浏览器端 `web/explorer` 大地图使用）。

仓库根目录::

    cd /path/to/「Source Epoch Incursion」   # 须为包含 game/ 的这一层目录（PowerShell）
    python -u -m game [--host HOST] [--port PORT]

    或在仓库根双击 / 运行 run_game_api.cmd（cmd）或 run_game_api.ps1（PowerShell，勿使用 cmd 的 cd /d）。

默认 ``127.0.0.1:8787``。环境变量：`GAME_API_HOST`、`GAME_API_PORT`。
其它配置见 `PROJECT_DOCUMENTATION`（如 `NARRATIVE_AI_DRY_RUN`）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    argv = list(sys.argv[1:])
    if argv and argv[0] == "serve":
        argv = argv[1:]

    inferred_repo_root = Path(__file__).resolve().parents[1]
    cwd = Path.cwd().resolve()
    if cwd != inferred_repo_root:
        print(
            f"[WARN] 当前 cwd 可能错误：cwd={cwd}\n"
            f"       请在本目录再启动 API：cd \"{inferred_repo_root}\"\n"
            f"       然后运行： python -u -m game\n"
            "       否则会连到不是我方仓库的源码，浏览器里 /api/health 会缺字段。\n",
            file=sys.stderr,
        )

    from .web_api import run_server

    ap = argparse.ArgumentParser(description="Story HTTP API for web/explorer")
    ap.add_argument("--host", default=os.environ.get("GAME_API_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("GAME_API_PORT", "8787")))
    args = ap.parse_args(argv)
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
