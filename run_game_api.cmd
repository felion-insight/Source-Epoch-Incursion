@echo off
REM 始终在「本脚本所在目录」启动，等价于在项目根运行 python -m game
cd /d "%~dp0"
echo cwd=%CD%
python -u -m game
pause
