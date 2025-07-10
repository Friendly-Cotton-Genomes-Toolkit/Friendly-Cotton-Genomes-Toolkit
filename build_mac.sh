#!/bin/bash

# ============================================================================
#      棉花基因组工具 (FCGT) Nuitka 专业打包脚本 (macOS)
#      Cotton Genomes Toolkit (FCGT) Nuitka Professional Build Script (macOS)
#
#      版本: v10 - 双语提示与环境预检最终版
#      Version: v10 - Bilingual & Pre-check Final Version
# ============================================================================

# --- 配置区 (Configuration) ---
APP_NAME="FCGT"
APP_VERSION="1.0.0"
MAIN_SCRIPT="main.py"
ICON_FILE="./ui/assets/logo.ico" # Nuitka在macOS上也可以使用.ico文件

# --- 目录结构定义 (Directory Definitions) ---
BUILD_ROOT="build_mac"
NUITKA_OUTPUT_DIR="$BUILD_ROOT"
RELEASE_DIR="$BUILD_ROOT/release"
FINAL_APP_NAME="${APP_NAME}.app"

# ============================================================================
#      步骤 0: 校验环境与参数 (Step 0: Verifying Environment & Arguments)
# ============================================================================
echo "[Step 0/4] 正在校验环境与参数... (Verifying environment & arguments...)"

# 校验 Python 解释器路径 (Check Python interpreter path)
if [ -z "$1" ]; then
    echo ""
    echo "[ERROR] 缺少 Python 解释器路径！"
    echo "        (Missing Python interpreter path!)"
    echo ""
    echo "用法 (Usage):"
    echo "    ./build_mac.sh /path/to/your/python3"
    echo ""
    exit 1
fi
PYTHON_EXE=$1
echo "   > Python 解释器 (Interpreter): $PYTHON_EXE"

# 检测 C++ 编译器 (Detect C++ Compiler - Clang)
if ! command -v clang &> /dev/null; then
    echo "[ERROR] 未找到 clang 编译器！"
    echo "        (clang compiler not found!)"
    echo "        请先安装 Xcode Command Line Tools, 运行: xcode-select --install"
    echo "        (Please install Xcode Command Line Tools by running: xcode-select --install)"
    exit 1
fi
echo "   > C++ 编译器 (Compiler): clang (已找到 / Found)"
echo ""

# ============================================================================
#      步骤 1: 创建干净的构建目录 (Step 1: Creating Clean Build Directories)
# ============================================================================
echo "[Step 1/4] 清理并创建构建目录... (Cleaning and creating build directories...)"
rm -rf "$BUILD_ROOT"
mkdir -p "$NUITKA_OUTPUT_DIR"
echo ""

# ============================================================================
#      步骤 2: Nuitka 编译 (Step 2: Nuitka Compilation)
# ============================================================================
echo "[Step 2/4] 开始 Nuitka 编译 (这可能需要很长时间，请耐心等待)..."
echo "           (Starting Nuitka compilation (this may take a long time, please be patient)...)"

"$PYTHON_EXE" -m nuitka \
    --standalone \
    --macos-create-app-bundle \
    --macos-app-icon="$ICON_FILE" \
    --enable-plugin=tk-inter \
    --include-package=pyyaml \
    --include-package=pandas \
    --include-package=openpyxl \
    --include-package=requests \
    --include-package=scipy \
    --include-package=statsmodels \
    --include-package=pkg_resources \
    --output-dir="$NUITKA_OUTPUT_DIR" \
    --include-data-dir=./ui/assets=ui/assets \
    --include-data-dir=./cotton_toolkit/locales=cotton_toolkit/locales \
    "$MAIN_SCRIPT"

if [ $? -ne 0 ]; then
    echo "[ERROR] Nuitka 编译失败！请检查上面的错误信息。"
    echo "        (Nuitka compilation failed! Please check the error messages above.)"
    exit 1
fi
echo ""

# ============================================================================
#      步骤 3: 移动并重命名最终产物 (Step 3: Moving and Renaming Final Product)
# ============================================================================
echo "[Step 3/4] 整理最终的 .app 文件... (Organizing final .app file...)"
# Nuitka会生成一个以 .app 结尾的文件夹，我们把它移动到 release 目录
mv "$NUITKA_OUTPUT_DIR/$MAIN_SCRIPT.app" "$RELEASE_DIR/$FINAL_APP_NAME"
echo ""

# ============================================================================
#      步骤 4: 清理临时文件 (Step 4: Cleaning up temporary files)
# ============================================================================
echo "[Step 4/4] 清理临时文件... (Cleaning up temporary files...)"
rm -rf "$NUITKA_OUTPUT_DIR/$MAIN_SCRIPT.build"
rm -rf "$NUITKA_OUTPUT_DIR/$MAIN_SCRIPT.dist" # 如果生成了这些中间目录，也一并清理
echo ""


echo "================================================================="
echo ""
echo "     打包成功！ (Build Succeeded!)"
echo ""
echo "     最终的应用程序包位于:"
echo "     (The final application bundle is located at:)"
echo "     $RELEASE_DIR/$FINAL_APP_NAME"
echo ""
echo "================================================================="