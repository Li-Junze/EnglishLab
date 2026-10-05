@echo off
cd /d "%~dp0"
title English Lab

set "ENVNAME=english"

rem ---------- 探测 conda 环境 ----------
set "ENVROOT=%USERPROFILE%\miniconda3\envs\%ENVNAME%"
if not exist "%ENVROOT%\pythonw.exe" set "ENVROOT=%USERPROFILE%\anaconda3\envs\%ENVNAME%"
if not exist "%ENVROOT%\pythonw.exe" set "ENVROOT=C:/ProgramData/miniconda3/envs/%ENVNAME%"
if not exist "%ENVROOT%\pythonw.exe" set "ENVROOT=C:/ProgramData/anaconda3/envs/%ENVNAME%"

if not exist "%ENVROOT%\pythonw.exe" (
    echo [X] 没有找到 english 环境的 pythonw.exe。
    echo.
    echo     已尝试的位置：
    echo       %USERPROFILE%\miniconda3\envs\%ENVNAME%
    echo       %USERPROFILE%\anaconda3\envs\%ENVNAME%
    echo       C:/ProgramData/miniconda3/envs/%ENVNAME%
    echo.
    echo     请先双击 init.bat 完成初始化。
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0main.py" (
    echo [X] 找不到 main.py
    pause
    exit /b 1
)

start "" "%ENVROOT%\pythonw.exe" "%~dp0main.py"
exit /b 0
