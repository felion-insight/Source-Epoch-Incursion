@echo off
REM 始终在「本脚本所在目录」启动，等价于在项目根运行 python -m game
REM 默认开启开发者调试 API（设置 GAME_DEBUG_API=0 可关闭）
cd /d "%~dp0"
echo cwd=%CD%
set GAME_DEBUG_API=1
python -u -m game
pause
