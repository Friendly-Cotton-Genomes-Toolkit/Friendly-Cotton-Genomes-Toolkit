import json
import requests
from typing import Dict, Any, Optional, List
import threading # 新增导入
import google.generativeai as genai


# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AIWrapper:
    def __init__(
            self,
            provider: str,
            api_key: str,
            model: str,
            base_url: Optional[str] = None,
            proxies: Optional[Dict[str, str]] = None
    ):
        if not provider or not api_key or not model:
            raise ValueError(_("AI服务商、API Key和模型名称不能为空。"))

        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.client = None  # 用于存放 Google SDK 客户端
        self.session = None  # 用于存放 requests session
        self.api_base = None  # 用于存放 OpenAI 兼容的 URL

        # --- 核心修改：根据服务商类型，初始化不同的客户端 ---
        if self.provider == 'google':
            if not genai:
                raise ImportError(_("缺少 'google-generativeai' 库，请运行 'pip install google-generativeai' 安装。"))
            # 配置Google SDK
            genai.configure(api_key=self.api_key, transport='rest', client_options={"api_key": self.api_key})
            self.client = genai.GenerativeModel(self.model)
        else:
            # 对于所有其他 OpenAI 兼容的接口
            if base_url:
                self.api_base = base_url.rstrip('/')
            else:
                provider_map = {
                    "openai": "https://api.openai.com/v1",
                    "deepseek": "https://api.deepseek.com/v1",
                    "qwen": "https://dashscope.aliyuncs.com/api/v1",
                    "siliconflow": "https://api.siliconflow.cn/v1",
                    "grok": "https://api.x.ai/v1",
                    "openai_compatible": "http://localhost:8080"
                }
                self.api_base = provider_map.get(provider.lower())

            if self.api_base is None:  # 如果是 None (例如，通用接口但未提供URL)
                raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

            self.session = requests.Session()
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            })
            if proxies:
                self.session.proxies.update(proxies)

    def _prepare_payload(self, prompt: str, temperature: float = 0.7) -> Dict[str, Any]:
        """根据不同的服务商准备请求体。"""
        if self.provider == "google":
            # Google Gemini API 的特定格式
            return {"contents": [{"parts": [{"text": prompt}]}]}
        else:
            # OpenAI 兼容的格式
            return {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }

    def _get_request_url(self) -> str:
        """根据不同的服务商获取请求URL。"""
        if self.provider == "google":
            return f"{self.api_base}/models/{self.model}:generateContent"
        else:
            return f"{self.api_base}/chat/completions"

    def _extract_response(self, response: requests.Response) -> str:
        """根据不同的服务商从响应中提取文本内容。"""
        response.raise_for_status()
        data = response.json()

        if self.provider == "google":
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        else:
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    def process(self, text: str, custom_prompt_template: str = "{text}", temperature: float = 0.7, timeout: int = 90) -> str:
        """
        【已修正错误处理】根据不同的服务商，使用对应的客户端处理单个文本。
        """
        prompt = custom_prompt_template.format(text=text)

        try:
            if self.provider == 'google':
                # --- Google SDK 调用 ---
                # 此处的错误由下方的通用 except Exception as e 捕获
                response = self.client.generate_content(prompt)
                return response.text.strip()
            else:
                # --- OpenAI 兼容接口调用 (使用 requests) ---
                # 此处的网络错误由下方的 except requests.exceptions.RequestException as e 专门捕获
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

        # --- 核心修改：分别捕获不同类型的异常 ---

        # 1. 专门捕获 requests 库的网络相关异常
        except requests.exceptions.RequestException as e:
            # 在这个块里，我们可以安全地访问 e.response
            error_message = f"{_('AI API请求失败 (requests):')} {e}"
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    # 尝试从更深的层级获取错误信息
                    msg = error_details.get('error', {}).get('message', str(error_details))
                    error_message += f"\n{_('服务商响应:')} {msg}"
                except json.JSONDecodeError:
                    error_message += f"\n{_('服务商响应 (非JSON):')} {e.response.text}"
            raise RuntimeError(error_message) from e

        # 2. 捕获所有其他类型的异常（包括Google SDK的错误）
        except Exception as e:
            # 在这个块里，我们不访问 e.response，因为它可能不存在
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
            genai.configure(api_key=api_key)
            models = genai.list_models()
            return sorted([m.name.replace("models/", "") for m in models if 'generateContent' in m.supported_generation_methods])
        else:
            # OpenAI 兼容接口的逻辑保持不变
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
            # 同样根据provider分流测试
            if provider == 'google':
                if not genai:
                    raise ImportError(_("缺少 'google-generativeai' 库。"))
                genai.configure(api_key=api_key)
                sdk_model = genai.GenerativeModel(model)
                # 使用一个非常短的超时和最大输出来测试
                response = sdk_model.generate_content("Hi", generation_config={"max_output_tokens": 5})
                if response.text:
                    return True, _("Google Gemini SDK 连接成功！")
                else:
                    return False, _("连接异常：收到了空响应。")
            else:
                # 对于其他兼容接口，使用我们自己封装的 process 方法来测试
                wrapper = cls(
                    provider=provider, api_key=api_key, model=model,
                    base_url=base_url, proxies=proxies
                )
                response_text = wrapper.process(text="Hi", temperature=0.1, timeout=timeout)
                if response_text:
                    return True, _("连接成功！配置有效。")
                else:
                    return False, _("连接异常：收到了空响应。")

        except Exception as e:
            error_type = type(e).__name__
            return False, f"{_('连接失败:')} {error_type}\n{_('详情:')} {str(e)}"



