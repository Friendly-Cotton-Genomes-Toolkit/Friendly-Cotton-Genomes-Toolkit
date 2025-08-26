import json
import requests
import logging
from typing import Dict, Any, Optional, List
import threading
import os
import contextlib

from requests.adapters import HTTPAdapter

# 尝试导入 google.generativeai，如果失败则优雅处理
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

# --- 使用统一的日志系统 ---
logger = logging.getLogger("cotton_toolkit.core.ai_wrapper")


@contextlib.contextmanager
def temp_proxies(proxies: Optional[Dict[str, str]]):
    """一个上下文管理器，用于临时设置代理环境变量。"""
    if not proxies:
        yield
        return

    original_proxies = {
        'http_proxy': os.environ.get('http_proxy'),
        'https_proxy': os.environ.get('https_proxy'),
    }

    http_p = proxies.get('http') or proxies.get('https')
    https_p = proxies.get('https') or proxies.get('http')

    if http_p: os.environ['http_proxy'] = http_p
    if https_p: os.environ['https_proxy'] = https_p

    try:
        yield
    finally:
        for key, value in original_proxies.items():
            if value:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]


class AIWrapper:
    def __init__(
            self,
            provider: str,
            api_key: str,
            model: str,
            base_url: Optional[str] = None,
            proxies: Optional[Dict[str, str]] = None,
            max_workers: int = 4
    ):
        if not provider or not api_key or not model:
            logger.error(_("AI服务商、API Key和模型名称不能为空。"))
            raise ValueError(_("AI服务商、API Key和模型名称不能为空。"))

        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.proxies = proxies
        self.client = None
        self.session = None
        self.api_base = None
        logger.info(_("正在初始化AI服务: {}").format(self.provider))

        if self.provider == 'google':
            if not genai:
                logger.error(_("缺少 'google-generativeai' 库。"))
                raise ImportError(_("缺少 'google-generativeai' 库，请运行 'pip install google-generativeai' 安装。"))
            with temp_proxies(self.proxies):
                genai.configure(api_key=self.api_key, transport='rest')
                self.client = genai.GenerativeModel(self.model)
        else:
            if base_url:
                self.api_base = base_url.rstrip('/')
            else:
                provider_map = {
                    "openai": "https://api.openai.com/v1",
                    "deepseek": "https://api.deepseek.com/v1",
                    "qwen": "https://dashscope.aliyuncs.com/api/v1",
                    "siliconflow": "https://api.siliconflow.cn/v1",
                    "grok": "https://api.x.ai/v1",
                }
                self.api_base = provider_map.get(provider.lower())

            if not self.api_base:
                logger.error(f"{_('不支持的服务商或缺少Base URL:')} {provider}")
                raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

            self.session = requests.Session()
            adapter = HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)

            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })
            if self.proxies:
                self.session.proxies.update(self.proxies)

    def process(self, text: str, custom_prompt_template: str = "{text}", temperature: float = 0.7,
                timeout: int = 90) -> str:
        prompt = custom_prompt_template.format(text=text)
        try:
            if self.provider == 'google':
                with temp_proxies(self.proxies):
                    response = self.client.generate_content(prompt)
                    return response.text.strip()
            else:
                url = f"{self.api_base}/chat/completions"
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                response = self.session.post(url, json=payload, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except requests.exceptions.RequestException as e:
            error_message = f"{_('AI API请求失败 (requests):')} {e}"
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    msg = error_details.get('error', {}).get('message', str(error_details))
                    error_message += f"\n{_('服务商响应:')} {msg}"
                except json.JSONDecodeError:
                    error_message += f"\n{_('服务商响应 (非JSON):')} {e.response.text}"
            logger.error(error_message)
            raise RuntimeError(error_message) from e
        except Exception as e:
            error_type = type(e).__name__
            error_message = f"{_('AI API处理时发生错误')} ({error_type}): {e}"
            logger.exception(error_message)
            raise RuntimeError(error_message) from e


    @staticmethod
    def get_models(
            provider: str,
            api_key: str,
            base_url: Optional[str] = None,
            cancel_event: Optional[threading.Event] = None,
            timeout: Optional[int] = 20,
            proxies: Optional[Dict[str, str]] = None
    ) -> List[str]:
        logger.info(_("正在获取AI模型列表..."))
        if not api_key:
            logger.error(_("API Key不能为空。"))
            raise ValueError(_("API Key不能为空。"))

        try:
            if provider == 'google':
                if not genai:
                    logger.error(_("缺少 'google-generativeai' 库。"))
                    raise ImportError(_("缺少 'google-generativeai' 库，请运行 'pip install google-generativeai' 安装。"))

                with temp_proxies(proxies):
                    genai.configure(api_key=api_key, transport='rest')
                    if cancel_event and cancel_event.is_set(): return []
                    models = genai.list_models()
                    return sorted([m.name.replace("models/", "") for m in models if
                                   'generateContent' in m.supported_generation_methods])
            else:
                if base_url:
                    api_base = base_url.rstrip('/')
                else:
                    provider_map = {
                        "openai": "https://api.openai.com/v1",
                        "deepseek": "https://api.deepseek.com/v1",
                        "qwen": "https://dashscope.aliyuncs.com/api/v1",
                        "siliconflow": "https://api.siliconflow.cn/v1",
                        "grok": "https://api.x.ai/v1",
                    }
                    api_base = provider_map.get(provider.lower())

                if not api_base:
                    logger.error(f"{_('不支持的服务商或缺少Base URL:')} {provider}")
                    raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

                url = f"{api_base}/models"
                headers = {"Authorization": f"Bearer {api_key}"}
                if cancel_event and cancel_event.is_set(): return []
                response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
                response.raise_for_status()
                models = response.json().get("data", [])
                return sorted([m["id"] for m in models])
        except Exception as e:
            logger.error(_("获取模型列表失败: {}").format(e))
            raise

    @classmethod
    def test_connection(
            cls,
            provider: str,
            api_key: str,
            model: str,
            base_url: Optional[str] = None,
            proxies: Optional[Dict[str, str]] = None,
            timeout: int = 20
    ) -> (bool, str):
        logger.info(_("正在测试AI连接..."))
        if not api_key or "YOUR_API_KEY" in api_key:
            raise ValueError(_("API Key 未配置或无效。"))
        if not model:
            raise ValueError(_("模型名称不能为空。"))

        try:
            with temp_proxies(proxies):
                if provider == 'google':
                    if not genai:
                        raise ImportError(_("缺少 'google-generativeai' 库。"))
                    genai.configure(api_key=api_key, transport='rest')
                    sdk_model = genai.GenerativeModel(model)
                    response = sdk_model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                    if response.text:
                        logger.info(_("Google Gemini SDK 连接成功！"))
                        return True, _("Google Gemini SDK 连接成功！")
                    else:
                        raise ConnectionError(_("连接异常：从服务商收到了空响应。"))

                else:
                    wrapper = cls(provider=provider, api_key=api_key, model=model, base_url=base_url, proxies=proxies)
                    response_text = wrapper.process(text="Hi", temperature=0.1, timeout=timeout)
                    if response_text:
                        logger.info(_("连接成功！配置有效。"))
                        return True, _("连接成功！配置有效。")
                    else:
                        raise ConnectionError(_("连接异常：从服务商收到了空响应。"))

        except Exception as e:
            error_type = type(e).__name__
            error_message = f"{_('连接测试失败:')} {error_type}\n{_('详情:')} {str(e)}"
            logger.error(error_message)
            raise RuntimeError(error_message) from e