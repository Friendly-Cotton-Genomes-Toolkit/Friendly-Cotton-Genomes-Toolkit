import subprocess
import sys
from typing import Tuple
import logging

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.utils.advanced_tools_test")


def check_muscle_executable(muscle_path: str) -> Tuple[bool, str]:
    """
    测试指定路径的 MUSCLE 可执行文件是否功能正常。
    Args:
        muscle_path: 指向 MUSCLE 可执行文件的路径。

    Returns:
        一个元组，包含:
        - bool: 如果测试成功则为 True，否则为 False。
        - str: 描述结果的消息（版本信息或错误详情）。
    """
    if not muscle_path:
        return False, "Path not configured."

    try:
        # 准备跨平台的 subprocess 参数
        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': 5,  # 5秒超时
            'check': False
        }
        if sys.platform == "win32":
            # 在Windows上隐藏可能弹出的命令行窗口
            kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        process = subprocess.run([muscle_path, "-version"], **kwargs)

        # MUSCLE v3.8将版本信息输出到stderr，v5输出到stdout
        if process.returncode == 0:
            version_info = (process.stdout or process.stderr).strip().split('\n')[0]
            return True, f"Success! ({version_info})"
        else:
            error_output = (process.stderr or process.stdout).strip()
            return False, f"Execution failed. Return code: {process.returncode}. Error: {error_output}"

    except FileNotFoundError:
        return False, "Execution failed. Check if the path is correct and the file has execute permissions."
    except subprocess.TimeoutExpired:
        return False, "Execution timed out. The program may be stuck."
    except Exception as e:
        return False, f"An unknown error occurred: {str(e)}"


def check_iqtree_executable(iqtree_path: str) -> Tuple[bool, str]:
    """
    测试指定路径的 IQ-TREE 可执行文件是否功能正常。

    Args:
        iqtree_path: 指向 IQ-TREE 可执行文件的路径。

    Returns:
        一个元组，包含:
        - bool: 如果测试成功则为 True，否则为 False。
        - str: 描述结果的消息（版本信息或错误详情）。
    """
    if not iqtree_path:
        return False, "Path not configured."

    try:
        # 准备跨平台的 subprocess 参数
        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': 5,
            'check': False
        }
        if sys.platform == "win32":
            kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        # IQ-TREE 使用 --version 来打印版本信息
        process = subprocess.run([iqtree_path, "--version"], **kwargs)

        # 成功的标志是返回码为0且输出中包含"IQ-TREE"
        if process.returncode == 0 and "IQ-TREE" in process.stdout:
            version_info = process.stdout.strip().split('\n')[0]
            return True, f"Success! ({version_info})"
        else:
            error_output = (process.stderr or process.stdout).strip()
            return False, f"Execution failed. Return code: {process.returncode}. Error: {error_output}"

    except FileNotFoundError:
        return False, "Execution failed. Check if the path is correct and the file has execute permissions."
    except subprocess.TimeoutExpired:
        return False, "Execution timed out. The program may be stuck."
    except Exception as e:
        return False, f"An unknown error occurred: {str(e)}"


def check_trimal_executable(trimal_path: str) -> Tuple[bool, str]:
    """
    测试指定路径的 trimAl 可执行文件是否功能正常。

    Args:
        trimal_path: 指向 trimAl 可执行文件的路径。

    Returns:
        一个元组，包含:
        - bool: 如果测试成功则为 True，否则为 False。
        - str: 描述结果的消息（版本信息或错误详情）。
    """
    if not trimal_path:
        return False, "Path not configured."

    try:
        # 准备跨平台的 subprocess 参数
        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': 5,
            'check': False
        }
        if sys.platform == "win32":
            kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW

        # trimAl 使用 -version 来打印版本信息
        process = subprocess.run([trimal_path, "--version"], **kwargs)

        # 成功的标志是返回码为0且输出中包含"trimAl version"
        if process.returncode == 0 and "trimAl" in process.stdout:
            version_info = process.stdout.strip().split('\n')[0]
            return True, f"Success! ({version_info})"
        else:
            error_output = (process.stderr or process.stdout).strip()
            return False, f"Execution failed. Return code: {process.returncode}. Error: {error_output}"

    except FileNotFoundError:
        return False, "Execution failed. Check if the path is correct and the file has execute permissions."
    except subprocess.TimeoutExpired:
        return False, "Execution timed out. The program may be stuck."
    except Exception as e:
        return False, f"An unknown error occurred: {str(e)}"