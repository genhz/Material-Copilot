"""
LLM 配置管理 - 从环境变量加载 LLM 配置

使用统一的环境变量名，直接修改 .env 文件中的值来切换提供商。
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


@dataclass
class LLMConfig:
    """LLM 配置数据类"""
    api_key: str
    base_url: str
    model: str

    @classmethod
    def load(cls) -> "LLMConfig":
        """
        从环境变量加载 LLM 配置

        Returns:
            LLMConfig: 配置对象

        Raises:
            ValueError: 如果 API Key 缺失
        """
        api_key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "")

        # 验证必要配置
        if not api_key:
            raise ValueError(
                "LLM_API_KEY 未配置。请在 .env 文件中设置 LLM_API_KEY"
            )

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def __repr__(self) -> str:
        return f"LLMConfig(model='{self.model}', base_url='{self.base_url}')"


# 全局配置实例（懒加载）
_config: Optional[LLMConfig] = None


def get_llm_config() -> LLMConfig:
    """
    获取全局 LLM 配置实例

    Returns:
        LLMConfig: 配置对象
    """
    global _config
    if _config is None:
        _config = LLMConfig.load()
    return _config


def reload_llm_config() -> LLMConfig:
    """
    重新加载 LLM 配置（用于热更新）

    Returns:
        LLMConfig: 新的配置对象
    """
    global _config
    _config = LLMConfig.load()
    return _config
