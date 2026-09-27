@echo off
chcp 65001 >nul
title PDF 合同重命名工具 - 打包脚本
echo ================================================
echo   PDF 合同重命名工具 - Windows EXE 打包脚本
echo ================================================
echo.
echo   打包完成后，生成的 exe 可直接复制到任意 Windows
echo   电脑运行，无需安装 Python，无需联网。
echo.

REM ---- 检查 Python ----
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo        https://www.python.org/downloads/
    echo        安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo [✓] Python 已安装
python --version

REM ---- 安装依赖 ----
echo.
echo [1/3] 安装依赖包...
pip install PyMuPDF rapidocr-onnxruntime Pillow pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败
    echo        如果是网络问题，可以尝试手动安装:
    echo        pip install PyMuPDF rapidocr-onnxruntime Pillow pyinstaller
    pause
    exit /b 1
)
echo [✓] 依赖安装完成

REM ---- 获取 rapidocr 路径 ----
echo.
echo [2/3] 定位 OCR 模型文件...
for /f "delims=" %%i in ('python -c "import rapidocr_onnxruntime as r; import os; print(os.path.dirname(r.__file__))"') do set RAPID_PATH=%%i
echo [✓] rapidocr 路径: %RAPID_PATH%

REM ---- PyInstaller 打包 ----
echo.
echo [3/3] 开始打包（需要几分钟，请耐心等待）...
echo.

pyinstaller ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --name "PDF合同重命名工具" ^
    --icon=NONE ^
    --add-data "%RAPID_PATH%;rapidocr_onnxruntime" ^
    --collect-all rapidocr_onnxruntime ^
    --collect-all onnxruntime ^
    --hidden-import PIL ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    pdf_contract_renamer.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息
    pause
    exit /b 1
)

echo.
echo ================================================
echo   [✓] 打包成功！
echo.
echo   输出目录: dist\PDF合同重命名工具\
echo   主程序:   dist\PDF合同重命名工具\PDF合同重命名工具.exe
echo.
echo   使用方法:
echo     1. 将整个 "PDF合同重命名工具" 文件夹复制到目标电脑
echo     2. 双击 PDF合同重命名工具.exe 即可运行
echo     3. 无需安装 Python，无需联网
echo.
echo   也支持命令行: PDF合同重命名工具.exe "C:\合同文件夹"
echo ================================================
pause
