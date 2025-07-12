# ============================================================================
#      棉花基因组工具 (FCGT) Nuitka 打包脚本 (v18 - 回归本质最终版)
#
#      功能:
#      1. 【核心】只使用 Nuitka 最核心、最稳定的参数，移除所有引起问题的插件。
#      2. 自动检测当前激活环境的 Python.exe，无需手动输入。
# ============================================================================

# --- 配置区 (Configuration) ---
$AppName = "FCGT"
$AppVersion = "1.0.0"
$MainScript = "main.py"
$IconFile = ".\ui\assets\logo.ico"
# 您可以根据需要调整核心数，或者直接注释掉下面两行，让 Nuitka 自动决定
$JobCount = 8 
$JobsParameter = "--jobs=$JobCount"

# --- 目录与文件名定义 ---
$ReleaseDir = ".\release"
$FinalExeName = "${AppName}_v${AppVersion}.exe"
$FinalExePath = "$ReleaseDir\$FinalExeName"

# ============================================================================
#      步骤 0: 校验环境
# ============================================================================
Write-Host "[Step 0/3] 正在校验环境... (Verifying environment...)" -ForegroundColor Green
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    Write-Host "[ERROR] 未能在您的 PATH 环境变量中找到 'python' 命令！" -ForegroundColor Red
    exit 1
}
$PythonExe = $PythonCommand.Source
Write-Host "   > 自动检测到 Python 解释器 (Auto-detected Interpreter): $PythonExe"
Write-Host "   > 将使用 $JobCount 个 CPU 核心进行编译 (Using $JobCount CPU cores for compilation)."
Write-Host ""

# ============================================================================
#      步骤 1: 清理
# ============================================================================
Write-Host "[Step 1/3] 清理旧的构建文件和发布目录... (Cleaning up...)" -ForegroundColor Green
if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
if (Test-Path $MainScript.Replace('.py', '.build')) { Remove-Item -Recurse -Force $MainScript.Replace('.py', '.build') }
if (Test-Path $MainScript.Replace('.py', '.dist')) { Remove-Item -Recurse -Force $MainScript.Replace('.py', '.dist') }
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
Write-Host ""

# ============================================================================
#      步骤 2: Nuitka 编译
# ============================================================================
Write-Host "[Step 2/3] 开始 Nuitka 编译... (Starting Nuitka compilation...)" -ForegroundColor Green

& $PythonExe -m nuitka `
    --onefile `
    $JobsParameter `
    --windows-console-mode=disable `
    --enable-plugin=tk-inter `
    --include-package=yaml `
    --include-package=pandas `
    --include-package=openpyxl `
    --include-package=requests `
    --include-package=scipy `
    --include-package=statsmodels `
    --include-package=pkg_resources `
    --windows-icon-from-ico=$IconFile `
    --include-data-dir=./ui/assets=ui/assets `
    --include-data-dir=./cotton_toolkit/locales=cotton_toolkit/locales `
    --output-dir=$ReleaseDir `
    --output-filename=$FinalExeName `
    $MainScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Nuitka 编译失败！请检查上面的错误信息。" -ForegroundColor Red
    exit 1
}
Write-Host ""

# ============================================================================
#      步骤 3: 最终成功信息
# ============================================================================
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "     打包成功！ (Build Succeeded!)" -ForegroundColor Cyan
Write-Host ""
Write-Host "     最终的单文件程序位于 (The final single-file executable is located at):" -ForegroundColor White
Write-Host "     $FinalExePath" -ForegroundColor Yellow
Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan