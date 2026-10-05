@echo off
cd /d "%~dp0"
title English Lab - 调试模式（保留窗口，显示错误）

set "ENVNAME=english"
set "ENVROOT=%USERPROFILE%\miniconda3\envs\%ENVNAME%"
if not exist "%ENVROOT%\python.exe" set "ENVROOT=%USERPROFILE%\anaconda3\envs\%ENVNAME%"
if not exist "%ENVROOT%\python.exe" set "ENVROOT=C:/ProgramData/miniconda3/envs/%ENVNAME%"
if not exist "%ENVROOT%\python.exe" set "ENVROOT=C:/ProgramData/anaconda3/envs/%ENVNAME%"

if not exist "%ENVROOT%\python.exe" (
    echo [X] 没有找到 english 环境的 python.exe，请先运行 init.bat
    pause
    exit /b 1
)

"%ENVROOT%\python.exe" "%~dp0main.py"
echo.
echo 程序已退出，退出码 = %errorlevel%
echo 上面的红色文字就是错误原因（如果有的话）。
pause
