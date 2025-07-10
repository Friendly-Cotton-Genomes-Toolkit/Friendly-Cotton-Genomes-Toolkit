@echo off
setlocal

:: ============================================================================
::      棉花基因组工具 (FCGT) Nuitka + 7-Zip/NanaZip 专业安装包生成脚本
::      Cotton Genomes Toolkit (FCGT) Nuitka + 7-Zip/NanaZip Professional Installer Script
::
::      版本: v10 - 双语提示与环境预检最终版
::      Version: v10 - Bilingual & Pre-check Final Version
::
::      功能 (Features):
::      1. 【关键优化】所有提示信息均为中英双语。 (All prompts are bilingual.)
::      2. 【关键优化】在编译前预先检查所有环境依赖 (Python路径, 压缩工具, SFX模块)。
::         (Pre-checks all environment dependencies before compilation.)
::      3. 从命令行接收 Python 解释器路径作为参数 (%1)。
::         (Accepts Python interpreter path as a command line argument (%1).)
:: ============================================================================

:: --- 配置区 (Configuration) ---
set APP_NAME=FCGT
set APP_VERSION=1.0.0
set MAIN_SCRIPT=main.py
set ICON_FILE=./ui/assets/logo.ico

:: --- 目录与文件名定义 (Directory & Filename Definitions) ---
set BUILD_DIR=build_temp
set RELEASE_DIR=release
set FINAL_INSTALLER_NAME=%APP_NAME%_v%APP_VERSION%_Installer.exe

:: ============================================================================
::      步骤 0: 校验环境与参数 (Step 0: Verifying Environment & Arguments)
:: ============================================================================
echo [Step 0/7] 正在校验环境与参数... (Verifying environment & arguments...)

:: 检查 Python 解释器路径 (Check Python interpreter path)
if "%~1"=="" (
    echo.
    echo [ERROR] 缺少 Python 解释器路径！
    echo         (Missing Python interpreter path!)
    echo.
    echo 用法 (Usage):
    echo     build.bat "C:\Your\Path\To\python.exe"
    echo.
    goto end
)
set PYTHON_EXE=%1
echo    ^> Python 解释器 (Interpreter): %PYTHON_EXE%

:: 检测压缩工具 (Detect archiver)
set "ARCHIVER="
where 7z.exe >nul 2>nul
if %errorlevel% equ 0 ( set "ARCHIVER=7z" )
if not defined ARCHIVER ( where NanaZip.Console.exe >nul 2>nul && set "ARCHIVER=NanaZip.Console" )
if not defined ARCHIVER (
    echo [ERROR] 未能找到 7-Zip 或 NanaZip！
    echo         (Could not find 7-Zip or NanaZip!)
    echo         请先安装并将其路径添加到系统的 PATH 环境变量中。
    echo         (Please install one and add it to your system's PATH environment variable.)
    goto end
)
echo    ^> 压缩工具 (Archiver): %ARCHIVER%

:: 【新增】检测 SFX 模块文件 (Check for SFX module file)
set SFX_MODULE=7zS.sfx
if not exist %SFX_MODULE% (
    echo [ERROR] 缺少 '%SFX_MODULE%' 文件！
    echo         (File '%SFX_MODULE%' is missing!)
    echo         请将 7-Zip 安装目录下的 '%SFX_MODULE%' 文件复制到本项目根目录。
    echo         (Please copy '%SFX_MODULE%' from your 7-Zip installation directory to the project root.)
    goto end
)
echo    ^> SFX 模块 (SFX Module): %SFX_MODULE% (已找到 / Found)
echo.

:: ============================================================================
::      步骤 1 到 7: 执行打包流程 (Step 1 to 7: Executing Build Process)
:: ============================================================================

:: 1. 清理旧的构建文件 (Clean up old build files)
echo [Step 1/7] 清理旧的构建文件... (Cleaning up old build files...)
if exist %BUILD_DIR% ( rmdir /s /q %BUILD_DIR% )
if exist %RELEASE_DIR% ( rmdir /s /q %RELEASE_DIR% )
if exist app_data.7z ( del app_data.7z )
if exist sfx_config.txt ( del sfx_config.txt )
mkdir %RELEASE_DIR%
echo.

:: 2. 使用 Nuitka 进行编译 (Compile with Nuitka)
echo [Step 2/7] 开始 Nuitka 编译 (这可能需要很长时间，请耐心等待)...
echo            (Starting Nuitka compilation (this may take a long time, please be patient)...)
%PYTHON_EXE% -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --enable-plugin=tk-inter ^
    --include-package=pyyaml ^
    --include-package=pandas ^
    --include-package=openpyxl ^
    --include-package=requests ^
    --include-package=scipy ^
    --include-package=statsmodels ^
    --include-package=pkg_resources ^
    --output-dir=%BUILD_DIR% ^
    --windows-icon-from-ico=%ICON_FILE% ^
    --include-data-dir=./ui/assets=ui/assets ^
    --include-data-dir=./cotton_toolkit/locales=cotton_toolkit/locales ^
    %MAIN_SCRIPT%

if %errorlevel% neq 0 (
    echo [ERROR] Nuitka 编译失败！请检查上面的错误信息。
    echo         (Nuitka compilation failed! Please check the error messages above.)
    goto end
)
echo.

:: 3. 创建 7-Zip 自解压配置文件 (Create 7-Zip SFX config file)
echo [Step 3/7] 创建 7-Zip 安装程序配置文件... (Creating 7-Zip SFX config file...)
(
    echo ;!@Install@!UTF-8!
    echo Title="%APP_NAME% %APP_VERSION% 安装向导 (Installation Wizard)"
    echo BeginPrompt="您想要安装 %APP_NAME% %APP_VERSION% 吗？\n\n程序将被安装到您选择的文件夹中。\n\nDo you want to install %APP_NAME% %APP_VERSION%?\nThe program will be installed in the folder you select."
    echo Progress="yes"
    echo RunProgram="%BUILD_DIR%\%MAIN_SCRIPT%.dist\%MAIN_SCRIPT%.exe"
    echo Shortcut="D", "%APP_NAME%.lnk", "", "%BUILD_DIR%\%MAIN_SCRIPT%.dist\%MAIN_SCRIPT%.exe"
    echo ;!@InstallEnd@!
) > sfx_config.txt
echo.

:: 4. 使用检测到的压缩工具创建数据压缩包 (Create data archive with the detected archiver)
echo [Step 4/7] 使用 %ARCHIVER% 压缩程序文件... (Archiving program files with %ARCHIVER%...)
%ARCHIVER% a -t7z app_data.7z .\%BUILD_DIR%\* -mx=9
if %errorlevel% neq 0 (
    echo [ERROR] %ARCHIVER% 压缩失败！ (%ARCHIVER% archiving failed!)
    goto end
)
echo.

:: 5. 合并文件，生成最终的安装包 (Combine files to create the final installer)
echo [Step 5/7] 合并文件，生成最终的安装程序... (Combining files to create the final installer...)
copy /b %SFX_MODULE% + sfx_config.txt + app_data.7z .\%RELEASE_DIR%\%FINAL_INSTALLER_NAME% > nul
if %errorlevel% neq 0 (
    echo [ERROR] 生成安装程序失败！ (Failed to create installer!)
    goto end
)
echo.

:: 6. 清理临时文件 (Clean up temporary files)
echo [Step 6/7] 清理临时文件... (Cleaning up temporary files...)
del app_data.7z
del sfx_config.txt
rmdir /s /q %BUILD_DIR%
echo.

:: 7. 最终成功信息 (Final success message)
echo =================================================================
echo.
echo      打包成功！ (Build Succeeded!)
echo.
echo      专业的安装程序已生成:
echo      (The professional installer has been generated at:)
echo      %RELEASE_DIR%\%FINAL_INSTALLER_NAME%
echo.
echo =================================================================

:end
pause