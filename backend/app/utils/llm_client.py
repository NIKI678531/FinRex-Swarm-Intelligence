"""
LLM客户端封装
统一使用OpenAI格式调用，支持 OpenAI / Azure OpenAI 两种后端
"""

import json
import os
import re
from typing import Optional, Dict, Any, List, Callable
from openai import OpenAI, AzureOpenAI

from ..config import Config


def _is_azure_endpoint(base_url: Optional[str]) -> bool:
    return bool(base_url) and ".openai.azure.com" in base_url


def _is_reasoning_model(model: Optional[str]) -> bool:
    """gpt-5 / o1 / o3 系列推理模型只支持 max_completion_tokens 且温度默认 1。"""
    if not model:
        return False
    lower = model.lower()
    return lower.startswith(("gpt-5", "o1", "o3", "o4"))


class LLMClient:
    """LLM客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        deployment_name: Optional[str] = None,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.deployment_name = deployment_name or Config.LLM_DEPLOYMENT_NAME or self.model

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.is_azure = _is_azure_endpoint(self.base_url)
        if self.is_azure:
            api_version = os.environ.get("LLM_API_VERSION") or "2024-12-01-preview"
            # 提取 azure_endpoint：去掉路径，保留 https://xxx.openai.azure.com
            match = re.match(r"^(https?://[^/]+)", self.base_url or "")
            azure_endpoint = match.group(1) if match else self.base_url
            self.client = AzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
            )
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）

        Returns:
            模型响应文本
        """
        kwargs: Dict[str, Any] = {
            "model": self.deployment_name if self.is_azure else self.model,
            "messages": messages,
        }

        if _is_reasoning_model(self.model):
            # 推理模型只接受默认温度且使用 max_completion_tokens
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        repair_fn: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            if repair_fn:
                repaired = repair_fn(cleaned_response)
                if repaired is not None:
                    return repaired
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}")

