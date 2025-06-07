import sys
from cx_Freeze import setup, Executable

# --- 需要包含在最终程序中的数据文件和目录 ---
include_files = [
    "icon.ico",
    "config.yml",
    "genome_sources_list.yml",
    # 如果您有 "cotton_toolkit/locales" 目录并且想包含它:
    # ("cotton_toolkit/locales", "locales"),
]

# --- cx_Freeze 的构建选项 ---
build_exe_options = {
    "packages": [
        "os", "sys", "yaml", "customtkinter", "tkinter", # 明确加入 tkinter
        "pandas", "requests", "gffutils", "numpy",
        "threading", "queue", "shutil", "gettext",
        "pkg_resources", "importlib_metadata" 
        "pillow",
        "win32gui", "win32con"
    ],
    "includes": [
        "cotton_toolkit", # 包含您的主包
        "tkinter.filedialog", # customtkinter 内部可能用到
        "tkinter.messagebox"
    ],
    "include_files": include_files,
    "excludes": [
        "tkinter.test", "unittest",
        "PyQt5", "PyQt6", "PySide2", "PySide6", # 明确排除所有可能的 Qt 绑定
        "matplotlib" # 如果 pandas 试图引入它，而你不需要，则排除
    ],
    # 有时需要指定DLL包含路径，但通常 cx_Freeze 能处理好
    # "bin_path_includes": [],
}

# --- 定义 GUI 版本 ---
gui_base = None
if sys.platform == "win32":
    gui_base = "Win32GUI"

gui_target = Executable(
    script="main.py",
    base=gui_base,
    icon="icon.ico",
    target_name="FCGT-GUI.exe"
)

# --- 定义 CLI 版本 ---
cli_target = Executable(
    script="cli_runner.py",
    base=None,
    target_name="FCGT.exe"
)

# --- 执行打包 ---
setup(
    name="Friendly Cotton Genomes Toolkit",
    version="0.0.1", # 增加一个小版本号
    description="一个用于棉花基因组分析的工具包",
    author="<您的名字>",
    options={"build_exe": build_exe_options},
    executables=[gui_target, cli_target]
)