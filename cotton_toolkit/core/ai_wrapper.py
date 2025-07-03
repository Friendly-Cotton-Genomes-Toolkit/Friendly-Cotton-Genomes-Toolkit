import json
import requests
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

    # 为 http 和 https 设置代理
    http_p = proxies.get('http') or proxies.get('https')
    https_p = proxies.get('https') or proxies.get('http')

    if http_p: os.environ['http_proxy'] = http_p
    if https_p: os.environ['https_proxy'] = https_p

    try:
        yield
    finally:
        # 恢复原始环境变量
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
            # 【核心修改1】新增 max_workers 参数
            max_workers: int = 4
    ):
        if not provider or not api_key or not model:
            raise ValueError(_("AI服务商、API Key和模型名称不能为空。"))

        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.proxies = proxies
        self.client = None
        self.session = None
        self.api_base = None

        if self.provider == 'google':
            if not genai:
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
                raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

            # 【核心修改2】配置一个与工作线程数匹配的连接池
            self.session = requests.Session()
            # 创建一个HTTP适配器，并设置连接池大小
            adapter = HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers)
            # 为http和https都挂载这个适配器
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
            raise RuntimeError(error_message) from e
        except Exception as e:
            error_type = type(e).__name__
            error_message = f"{_('AI API处理时发生错误')} ({error_type}): {e}"
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
        if not api_key:
            raise ValueError(_("API Key不能为空。"))

        if provider == 'google':
            if not genai:
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
                raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

            url = f"{api_base}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            if cancel_event and cancel_event.is_set(): return []
            response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
            response.raise_for_status()
            models = response.json().get("data", [])
            return sorted([m["id"] for m in models])

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
        if not api_key or "YOUR_API_KEY" in api_key:
            return False, _("API Key 未配置或无效。")
        if not model:
            return False, _("模型名称不能为空。")

        try:
            with temp_proxies(proxies):
                if provider == 'google':
                    if not genai:
                        raise ImportError(_("缺少 'google-generativeai' 库。"))
                    genai.configure(api_key=api_key, transport='rest')
                    sdk_model = genai.GenerativeModel(model)
                    response = sdk_model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                    if response.text:
                        return True, _("Google Gemini SDK 连接成功！")
                    else:
                        return False, _("连接异常：收到了空响应。")
                else:
                    wrapper = cls(provider=provider, api_key=api_key, model=model, base_url=base_url, proxies=proxies)
                    response_text = wrapper.process(text="Hi", temperature=0.1, timeout=timeout)
                    if response_text:
                        return True, _("连接成功！配置有效。")
                    else:
                        return False, _("连接异常：收到了空响应。")
        except Exception as e:
            error_type = type(e).__name__
            return False, f"{_('连接失败:')} {error_type}\n{_('详情:')} {str(e)}"