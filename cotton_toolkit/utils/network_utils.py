# cotton_toolkit/utils/network_utils.py
import logging
from typing import Tuple, Dict

import requests

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.utils.network_utils")


def test_proxy(proxies: Dict[str, str]) -> Tuple[bool, str]:
    """
    通过代理连接到一个测试站点，并返回连接结果。

    Args:
        proxies (Dict[str, str]): 包含 'http' 和/或 'https' 键的代理字典。

    Returns:
        Tuple[bool, str]: 一个元组，包含成功状态和结果消息。
    """
    test_url = "https://httpbin.org/get"
    logger.info(_("正在通过代理 {} 测试与 {} 的连接...").format(proxies, test_url))

    try:
        response = requests.get(test_url, proxies=proxies, timeout=15)
        response.raise_for_status()  # 如果状态码不是 2xx，则引发异常

        origin_ip = response.json().get('origin', 'N/A')
        message = f"{_('连接成功！')}\n{_('测试站点报告的IP地址是:')} {origin_ip}"
        logger.info(_("代理测试成功，报告的IP为 {}").format(origin_ip))
        return True, message

    except requests.exceptions.RequestException as e:
        error_message = f"{_('连接失败。')}\n{_('错误详情:')} {e}"
        logger.error(_("代理测试失败: {}").format(e))
        return False, error_message