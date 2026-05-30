@echo off
REM ============================================================
REM  源纪元 · 岸线侵入  —  一键启动（Windows CMD）
REM  同时启动 游戏API(8787) + 静态文件服务(8080)
REM ============================================================
cd /d "%~dp0"

echo.
echo ============================================================
echo   源纪元 · 岸线侵入  服务器启动中...
echo ============================================================
echo.
echo   游戏 API  : http://127.0.0.1:8787
echo   大地图页面 : http://127.0.0.1:8080/web/explorer/
echo   状态检查   : http://127.0.0.1:8787/api/health
echo.
echo   按 Ctrl+C 停止所有服务
echo ============================================================
echo.

REM 启动游戏 API（后台窗口）
start "Source Epoch - Game API" cmd /c "cd /d "%CD%" && set GAME_DEBUG_API=0 && python -u -m game"

REM 稍等让 API 先启动
timeout /t 2 /nobreak >nul

REM 启动静态文件服务器（当前窗口）
echo [静态服务] 启动中...
python -m http.server 8080 --bind 127.0.0.1
pause
