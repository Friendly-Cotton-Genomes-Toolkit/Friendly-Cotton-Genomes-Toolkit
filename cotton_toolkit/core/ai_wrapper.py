# cotton_toolkit/core/ai_wrapper.py

from typing import Optional, List, Dict, Any
import httpx
import logging

# 确保您已安装 openai 库: pip install openai
try:
    from openai import OpenAI
except ImportError:
    # 如果在没有安装openai库的环境中，这个错误将在第一次尝试使用时被捕获
    OpenAI = None

logger = logging.getLogger("cotton_toolkit.ai_wrapper")


class AIWrapper:
    """
    一个通用的AI模型API客户端封装。
    支持任何兼容OpenAI API格式的服务 (包括Google AI Studio, Groq等)。
    """

    def __init__(self, api_key: str, model: str, base_url: str, proxy_url: Optional[str] = None):
        """
        初始化AI客户端。

        Args:
            api_key (str): 您的API密钥。
            model (str): 您要使用的模型名称。
            base_url (str): API的端点地址。
            proxy_url (Optional[str]): (可选) HTTP/HTTPS 代理地址。
        """
        if OpenAI is None:
            raise ImportError("AI Wrapper需要 'openai' 库。请运行: pip install openai")

        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.proxy_url = proxy_url

        http_client = None
        if self.proxy_url:
            try:
                transport = httpx.HTTPTransport(proxy=self.proxy_url)
                http_client = httpx.Client(transport=transport)
                logger.info(f"AI Wrapper: 已配置代理 {self.proxy_url}")
            except Exception as e:
                logger.warning(f"AI Wrapper 警告: 配置代理失败 - {e}")

        try:
            self.client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                http_client=http_client,
            )
            logger.info(f"AI Wrapper: 客户端初始化成功。端点: {self.base_url}, 模型: {self.model}")
        except Exception as e:
            raise ConnectionError(f"AI Wrapper: 初始化客户端失败: {e}")

    def get_completion(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """
        获取AI模型的文本补全。

        Args:
            system_prompt (str): 系统提示词，定义AI的角色。
            user_prompt (str): 用户的具体问题或指令。
            temperature (float): 控制生成文本的随机性。

        Returns:
            str: AI模型的回复文本。
        """
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=self.model,
                temperature=temperature,
            )
            # 确保返回的是字符串
            response_content = chat_completion.choices[0].message.content
            return response_content if response_content is not None else ""
        except Exception as e:
            error_message = f"AI API调用失败: {e}"
            logger.error(error_message)
            # 返回错误信息，而不是让程序崩溃
            return error_message