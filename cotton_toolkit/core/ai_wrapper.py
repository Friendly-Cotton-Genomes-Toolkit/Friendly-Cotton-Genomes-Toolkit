# cotton_toolkit/core/ai_wrapper.py

import os
import json
import requests
from typing import Dict, Any, Optional, Callable
import threading # 新增导入

# 全局翻译函数占位符
try:
    from builtins import _
except ImportError:
    def _(s):
        return s


class AIWrapper:
    def __init__(self, provider: str, api_key: str, model: str, base_url: Optional[str] = None):
        if not provider or not api_key or not model:
            raise ValueError(_("AI服务商、API Key和模型名称不能为空。"))

        self.provider = provider
        self.api_key = api_key
        self.model = model

        # --- 【核心修改】处理不同的API Base URL ---
        if base_url:
            self.api_base = base_url.rstrip('/')
        else:
            provider_map = {
                "google": "https://generativelanguage.googleapis.com/v1beta",
                "openai": "https://api.openai.com/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "qwen": "https://dashscope.aliyuncs.com/api/v1",
                "siliconflow": "https://api.siliconflow.cn/v1",
            }
            self.api_base = provider_map.get(provider.lower())

        if not self.api_base:
            raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def _prepare_payload(self, prompt: str) -> Dict[str, Any]:
        """根据不同的服务商准备请求体。"""
        if self.provider == "google":
            return {"contents": [{"parts": [{"text": prompt}]}]}
        else:  # OpenAI-compatible
            return {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            }

    def _get_request_url(self) -> str:
        """根据不同的服务商获取请求URL。"""
        if self.provider == "google":
            return f"{self.api_base}/models/{self.model}:generateContent"
        else:  # OpenAI-compatible
            return f"{self.api_base}/chat/completions"

    def _extract_response(self, response: requests.Response) -> str:
        """根据不同的服务商从响应中提取文本内容。"""
        response.raise_for_status()
        data = response.json()

        if self.provider == "google":
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        else:  # OpenAI-compatible
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

    def process(self, text: str, custom_prompt_template: str = "{text}") -> str:
        """处理单个文本，支持自定义提示词模板。"""
        prompt = custom_prompt_template.format(text=text)
        url = self._get_request_url()
        payload = self._prepare_payload(prompt)

        try:
            response = self.session.post(url, json=payload, timeout=90)
            return self._extract_response(response)
        except requests.exceptions.RequestException as e:
            error_message = f"{_('AI API请求失败:')} {e}"
            # 尝试从响应体中获取更详细的错误信息
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    error_message += f"\n{_('服务商响应:')} {error_details.get('error', {}).get('message', e.response.text)}"
                except json.JSONDecodeError:
                    error_message += f"\n{_('服务商响应 (非JSON):')} {e.response.text}"
            raise RuntimeError(error_message) from e

    @staticmethod
    def get_models(provider: str, api_key: str, base_url: Optional[str] = None,
                   cancel_event: Optional[threading.Event] = None, timeout: Optional[int] = None,
                   proxies: Optional[Dict[str, str]] = None) -> list[str]:  # 【新增】proxies 参数
        """静态方法，用于获取指定服务商的模型列表。"""
        if not api_key:
            raise ValueError(_("API Key不能为空。"))

        if base_url:
            api_base = base_url.rstrip('/')
        else:
            provider_map = {
                "google": "https://generativelanguage.googleapis.com/v1beta",
                "openai": "https://api.openai.com/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "qwen": "https://dashscope.aliyuncs.com/api/v1",
                "siliconflow": "https://api.siliconflow.cn/v1",
                "grok": "https://api.x.ai/v1",  # 添加grok的默认查找地址
            }
            api_base = provider_map.get(provider.lower())

        if not api_base:
            raise ValueError(f"{_('不支持的服务商或缺少Base URL:')} {provider}")

        headers = {"Authorization": f"Bearer {api_key}"}

        # Google的API比较特殊
        if provider == 'google':
            url = f"{api_base}/models"
            # 将 proxies 传递给 requests.get
            response = requests.get(url, headers=headers, params={"pageSize": 1000}, timeout=timeout, proxies=proxies)
            response.raise_for_status()
            models = response.json().get("models", [])
            # 过滤出支持generateContent的模型
            return sorted([
                m["name"] for m in models
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ])
        else:  # OpenAI-compatible
            url = f"{api_base}/models"
            # 将 proxies 传递给 requests.get
            response = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
            response.raise_for_status()
            models = response.json().get("data", [])
            return sorted([m["id"] for m in models])