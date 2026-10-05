@echo off
cd /d "%~dp0"
title English Lab - 环境初始化

set "ENVNAME=english"
set "PYVER=3.11"
set "MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

echo ============================================
echo   English Lab  环境初始化
echo ============================================
echo.

rem ---------- 1. 定位 conda ----------
set "CONDA_BASE=%USERPROFILE%\miniconda3"
if not exist "%CONDA_BASE%\condabin\conda.bat" set "CONDA_BASE=%USERPROFILE%\anaconda3"
if not exist "%CONDA_BASE%\condabin\conda.bat" set "CONDA_BASE=C:/ProgramData/miniconda3"
if not exist "%CONDA_BASE%\condabin\conda.bat" set "CONDA_BASE=C:/ProgramData/anaconda3"
if not exist "%CONDA_BASE%\condabin\conda.bat" set "CONDA_BASE=C:/ProgramData/Anaconda3"

if not exist "%CONDA_BASE%\condabin\conda.bat" (
    echo [X] 没有找到 conda。
    echo.
    echo     请把 Miniconda / Anaconda 安装到下面位置之一：
    echo       %USERPROFILE%\miniconda3
    echo       %USERPROFILE%\anaconda3
    echo       C:/ProgramData/miniconda3
    echo.
    pause
    exit /b 1
)
echo [0/3] conda 位于: %CONDA_BASE%

rem ---------- 2. 创建环境 ----------
set "ENVPY=%CONDA_BASE%\envs\%ENVNAME%\python.exe"
if exist "%ENVPY%" (
    echo [1/3] 环境 %ENVNAME% 已存在，跳过创建。
) else (
    echo [1/3] 正在创建 conda 环境 %ENVNAME%，python %PYVER%，请耐心等待...
    call "%CONDA_BASE%\condabin\conda.bat" create -n %ENVNAME% python=%PYVER% -y
    if errorlevel 1 (
        echo.
        echo [X] 环境创建失败。请检查网络后重新运行 init.bat
        pause
        exit /b 1
    )
)

if not exist "%ENVPY%" (
    echo [X] 环境目录异常，未找到 %ENVPY%
    echo     请删除目录 %CONDA_BASE%\envs\%ENVNAME% 后重试。
    pause
    exit /b 1
)

rem ---------- 3. 安装依赖 ----------
echo [2/3] 正在安装依赖（清华镜像），大约需要 1-3 分钟...
"%ENVPY%" -m pip install -i %MIRROR% --timeout 180 --retries 5 -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo [X] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

rem ---------- 4. 校验 ----------
"%ENVPY%" -c "import PyQt5, requests; print('deps ok')"
if errorlevel 1 (
    echo [X] 依赖校验未通过。
    pause
    exit /b 1
)

rem ---------- 5. 记录环境路径 ----------
echo [3/3] 写入 _env.txt
> "%~dp0_env.txt" echo %CONDA_BASE%\envs\%ENVNAME%

echo.
echo ============================================
echo   初始化完成！以后双击 start.bat 即可运行。
echo ============================================
echo.
pause
