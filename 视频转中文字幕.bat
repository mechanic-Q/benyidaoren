@echo off
rem 日语视频 -> 中文字幕 一键工具 (Windows 双击/拖拽)
rem 用法: 把视频文件拖到本 bat 图标上
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo 请把日语视频文件拖到本窗口上，然后回车
    set /p VPATH=
) else (
    set "VPATH=%~1"
)

if not exist "!VPATH!" (
    echo [错误] 文件不存在: !VPATH!
    pause
    exit /b 1
)

echo.
echo ====== 日语视频转中文字幕 ======
echo 视频: !VPATH!
echo ================================
echo.

rem 转 WSL 路径并调用 (wsl.exe 用全路径)
for /f "delims=" %%i in ('wsl.exe -d Ubuntu -- wslpath -u "!VPATH!"') do set "WVPATH=%%i"
echo WSL路径: !WVPATH!
echo.

wsl.exe -d Ubuntu -- bash -lc "python3 /home/lmr/tools/ja2zh_subtitle/ja2zh_subtitle.py '!WVPATH!' --keep-ja"

echo.
echo 完成! 字幕文件在视频同目录: 视频名.zh.srt
pause
