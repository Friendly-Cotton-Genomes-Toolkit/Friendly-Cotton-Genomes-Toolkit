#!/bin/bash

# ============================================================================
#      棉花基因组工具 (FCGT) Nuitka 专业打包脚本 (Linux)
#      Cotton Genomes Toolkit (FCGT) Nuitka Professional Build Script (Linux)
#
#      版本: v10 - 双语提示与环境预检最终版
#      Version: v10 - Bilingual & Pre-check Final Version
# ============================================================================

# --- 配置区 (Configuration) ---
APP_NAME="FCGT"
APP_VERSION="1.0.0"
MAIN_SCRIPT="main.py"
# 在Linux上，图标通常通过 .desktop 文件处理，Nuitka命令中不直接指定

# --- 目录结构定义 (Directory Definitions) ---
BUILD_ROOT="build_linux"
NUITKA_OUTPUT_DIR="$BUILD_ROOT/standalone"
RELEASE_DIR="$BUILD_ROOT/release"
FINAL_ARCHIVE_NAME="${APP_NAME}_v${APP_VERSION}_Linux.tar.gz"

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
    echo "    ./build.sh /path/to/your/python3"
    echo ""
    exit 1
fi
PYTHON_EXE=$1
echo "   > Python 解释器 (Interpreter): $PYTHON_EXE"

# 检测 C++ 编译器 (Detect C++ Compiler)
if ! command -v g++ &> /dev/null; then
    echo "[ERROR] 未找到 g++ 编译器！"
    echo "        (g++ compiler not found!)"
    echo "        在 Debian/Ubuntu 上，请运行: sudo apt-get install build-essential"
    echo "        (On Debian/Ubuntu, please run: sudo apt-get install build-essential)"
    exit 1
fi
echo "   > C++ 编译器 (Compiler): g++ (已找到 / Found)"
echo ""

# ============================================================================
#      步骤 1: 创建干净的构建目录 (Step 1: Creating Clean Build Directories)
# ============================================================================
echo "[Step 1/4] 清理并创建构建目录... (Cleaning and creating build directories...)"
rm -rf "$BUILD_ROOT"
mkdir -p "$NUITKA_OUTPUT_DIR"
mkdir -p "$RELEASE_DIR"
echo ""

# ============================================================================
#      步骤 2: Nuitka 编译 (Step 2: Nuitka Compilation)
# ============================================================================
echo "[Step 2/4] 开始 Nuitka 编译 (这可能需要很长时间，请耐心等待)..."
echo "           (Starting Nuitka compilation (this may take a long time, please be patient)...)"

"$PYTHON_EXE" -m nuitka \
    --standalone \
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
#      步骤 3: 创建可分发的压缩包 (Step 3: Creating Distributable Archive)
# ============================================================================
echo "[Step 3/4] 创建 .tar.gz 压缩包... (Creating .tar.gz archive...)"
# main.py.dist 是 Nuitka 生成的实际程序文件夹
cd "$NUITKA_OUTPUT_DIR/$MAIN_SCRIPT.dist"
tar -czf "../../$RELEASE_DIR/$FINAL_ARCHIVE_NAME" .
cd ../../..  # 返回项目根目录
echo ""

# ============================================================================
#      步骤 4: 清理临时文件 (Step 4: Cleaning up temporary files)
# ============================================================================
echo "[Step 4/4] 清理临时文件... (Cleaning up temporary files...)"
rm -rf "$NUITKA_OUTPUT_DIR"
echo ""

echo "================================================================="
echo ""
echo "     打包成功！ (Build Succeeded!)"
echo ""
echo "     最终的可分发压缩包位于:"
echo "     (The final distributable archive is located at:)"
echo "     $RELEASE_DIR/$FINAL_ARCHIVE_NAME"
echo ""
echo "================================================================="