# cotton_toolkit/utils/tool_validator.py
import subprocess
import sys
import logging
import os  # 新增导入 os 模块
from typing import Tuple

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.utils.tool_validator")


def _run_command(cmd: list, cwd: str = None) -> Tuple[bool, str, str]:
    """
    通用命令执行辅助函数，返回 (是否成功运行, stdout, stderr)
    【已修改】: 增加 cwd 参数
    """
    try:
        # 在Windows上使用CREATE_NO_WINDOW来防止命令行窗口闪烁
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            errors='ignore',
            creationflags=creationflags,
            timeout=5,
            cwd=cwd  # 【新增】设置命令的当前工作目录
        )
        return True, result.stdout, result.stderr
    except FileNotFoundError:
        return False, "", _("命令或程序 '{}' 未找到。请检查路径是否正确。").format(cmd[0])
    except subprocess.TimeoutExpired:
        # 【新增】捕获超时异常
        return False, "", _(
            "命令执行超时（超过5秒）。\n请检查选择的程序是否为非交互式命令行工具（例如，对于PAML，应选择 codeml 而不是 paml）。").format(
            cmd[0])
    except Exception as e:
        return False, "", _("执行命令时发生未知错误: {}").format(e)


def check_muscle_executable(muscle_path: str) -> Tuple[bool, str]:
    """检查 MUSCLEv5 可执行文件是否有效。"""
    if not muscle_path:
        return False, _("错误: 未提供 MUSCLE 的路径。")

    # 【新增】设置 cwd
    tool_dir = os.path.dirname(muscle_path)
    ran_successfully, stdout, stderr = _run_command([muscle_path, "--version"], cwd=tool_dir)
    output = stdout + stderr

    if ran_successfully and "muscle" in output.lower():
        return True, _("检测成功！\n{}").format(output.strip())
    else:
        return False, _("MUSCLE 测试失败。请确保路径指向有效的 MUSCLE v5 可执行文件。\n错误详情: {}").format(
            output or stderr)


def check_iqtree_executable(iqtree_path: str) -> Tuple[bool, str]:
    """检查 IQ-TREE 可执行文件是否有效。"""
    if not iqtree_path:
        return False, _("错误: 未提供 IQ-TREE 的路径。")

    # 【新增】设置 cwd
    tool_dir = os.path.dirname(iqtree_path)
    ran_successfully, stdout, stderr = _run_command([iqtree_path, "-h"], cwd=tool_dir)
    output = stdout + stderr

    if ran_successfully and "IQ-TREE" in output:
        return True, _("检测成功！\nIQ-TREE 版本信息检测成功。")
    else:
        return False, _("IQ-TREE 测试失败。请确保路径指向有效的 IQ-TREE 可执行文件。\n错误详情: {}").format(
            output or stderr)


def check_trimal_executable(trimal_path: str) -> Tuple[bool, str]:
    """检查 trimAl 可执行文件是否有效。"""
    if not trimal_path:
        return False, _("错误: 未提供 trimAl 的路径。")

    # 【新增】设置 cwd
    tool_dir = os.path.dirname(trimal_path)
    ran_successfully, stdout, stderr = _run_command([trimal_path, "--version"], cwd=tool_dir)
    output = stdout + stderr

    if ran_successfully and "trimAl" in output:
        return True, _("检测成功！\n{}").format(output.strip())
    else:
        return False, _("trimAl 测试失败。请确保路径指向有效的 trimAl 可执行文件。\n错误详情: {}").format(
            output or stderr)


def check_perl_command(perl_path: str) -> Tuple[bool, str]:
    """检查 Perl 命令是否可用。"""
    cmd = perl_path or "perl"
    # Perl 通常是系统命令，不需要设置cwd
    ran_successfully, stdout, stderr = _run_command([cmd, "-v"])
    output = stdout + stderr

    if ran_successfully and "this is perl" in output.lower():
        return True, _("Perl 环境可用。\n{}").format(output.strip())
    else:
        return False, _(
            "Perl 命令执行失败。请确保已正确安装Perl (例如 Strawberry Perl for Windows) 并且路径配置正确。\n错误详情: {}").format(
            output or stderr)


def check_pal2nal_script(perl_path: str, pal2nal_path: str) -> Tuple[bool, str]:
    """检查 PAL2NAL 脚本是否可以通过 Perl 成功调用。"""
    if not pal2nal_path:
        return False, _("错误: 未提供 pal2nal.pl 脚本的路径。")

    perl_cmd = perl_path or "perl"
    # Perl 脚本通常也不需要设置cwd
    ran_successfully, stdout, stderr = _run_command([perl_cmd, pal2nal_path])
    output = stdout + stderr

    if "pal2nal" in output.lower():
        return True, _("PAL2NAL 脚本可被Perl成功调用。")
    else:
        return False, _("PAL2NAL 脚本执行失败。请检查Perl路径和脚本路径是否正确。\n错误详情: {}").format(output or stderr)


def check_paml_executable(paml_path: str) -> Tuple[bool, str]:
    """检查 PAML (codeml) 可执行文件是否有效。"""
    if not paml_path:
        return False, _("错误: 未提供 PAML (codeml) 的路径。")

    # 【新增】为 PAML 设置 cwd，这是最关键的修复
    tool_dir = os.path.dirname(paml_path)
    ran_successfully, stdout, stderr = _run_command([paml_path], cwd=tool_dir)
    output = stdout + stderr

    if "codeml" in output.lower():
        return True, _("PAML (codeml) 可执行。")
    else:
        return False, _("PAML (codeml) 执行失败。请检查路径是否为 codeml 程序本身。\n错误详情: {}").format(
            output or stderr)


def check_codonw_executable(codonw_path: str) -> Tuple[bool, str]:
    """检查 CodonW 可执行文件是否有效。"""
    if not codonw_path:
        return False, _("错误: 未提供 CodonW 的路径。")

    # 【新增】为 CodonW 设置 cwd，作为稳健性改进
    tool_dir = os.path.dirname(codonw_path)
    ran_successfully, stdout, stderr = _run_command([codonw_path, "-nomenu"], cwd=tool_dir)
    output = stdout + stderr

    if "codonw" in output.lower():
        return True, _("CodonW 可执行。")
    else:
        return False, _("CodonW 执行失败。请确保路径是否正确。\n错误详情: {}").format(output or stderr)