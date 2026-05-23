@echo off
REM 第二终端：在仓库根提供静态页（8080）。大地图须走此端口；剧情 API 仍是 8787（另开 python -m game）。
cd /d "%~dp0"
echo.
echo 静态根目录: %CD%
echo 大地图:     http://127.0.0.1:8080/web/explorer/
echo 根跳转页:   http://127.0.0.1:8080/
echo 须另开终端运行 API: python -u -m game  或 run_game_api.cmd / restart_game_api.cmd
echo 按 Ctrl+C 停止本服务
echo.
python -m http.server 8080 --bind 127.0.0.1
