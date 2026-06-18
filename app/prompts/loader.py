"""Prompt Registry: YAML + Jinja2 模板加载与渲染引擎。

用法:
    from app.prompts import get_prompt

    # 加载纯文本 prompt
    prompt = get_prompt("chat/system")

    # 加载并渲染带变量的 prompt
    prompt = get_prompt("analysis/system", blogger_context="...", author_handle="elonmusk", content="...")

    # 指定版本
    prompt = get_prompt("chat/system", version="v1.1")

文件结构:
    prompts/
      chat.yaml          — chat_agent 各节 prompt
      supervisor.yaml    — 分类 prompt (system + human)
      analysis.yaml      — 分析 prompt
      risk.yaml          — 风险评估 prompt
      signal.yaml        — 信号分析 prompt
      report.yaml        — 报告 section + synthesis prompt
      sql.yaml           — SQL agent prompt + DDL
      self_query.yaml    — 查询意图解析 prompt
      memory.yaml        — 压缩/偏好提取 prompt
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml
from jinja2 import BaseLoader, Environment, TemplateError
from loguru import logger

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_jinja_env = Environment(
    loader=BaseLoader(),
    keep_trailing_newline=True,
)


@functools.lru_cache(maxsize=128)
def _load_yaml(filename: str) -> dict:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data


def get_prompt(key: str, version: str | None = None, **variables) -> str:
    """加载并渲染 prompt 模板。

    Args:
        key: prompt 标识，格式为 "<file>/<name>"，如 "chat/system"
        version: 可选版本标签，默认使用 YAML 中 is_active=true 的版本
        **variables: Jinja2 模板变量

    Returns:
        渲染后的 prompt 字符串
    """
    filename, name = key.split("/", 1)
    filename = f"{filename}.yaml"

    data = _load_yaml(filename)
    prompts = data.get("prompts", {})
    entry = prompts.get(name)
    if entry is None:
        raise KeyError(f"Prompt '{key}' not found in {filename}")

    # 选择版本
    if isinstance(entry, dict) and "versions" in entry:
        versions = entry["versions"]
        if version:
            template_text = versions.get(version)
            if template_text is None:
                raise KeyError(f"Version '{version}' not found for prompt '{key}'")
        else:
            # 使用 is_active=True 的版本，或取最后一个
            active = None
            for v_name, v_text in versions.items():
                if isinstance(v_text, dict) and v_text.get("is_active"):
                    active = v_text["content"]
                    break
                elif isinstance(v_text, str):
                    active = v_text  # fallback: last simple string
            template_text = active or list(versions.values())[-1]
            if isinstance(template_text, dict):
                template_text = template_text["content"]
    elif isinstance(entry, dict) and "content" in entry:
        template_text = entry["content"]
    elif isinstance(entry, dict) and "system" in entry:
        # Multi-message prompt: return system text by default
        template_text = entry["system"]
    elif isinstance(entry, str):
        template_text = entry
    else:
        raise ValueError(f"Unexpected format for prompt '{key}': {type(entry)}")

    # Jinja2 渲染
    if variables:
        try:
            template = _jinja_env.from_string(template_text)
            return template.render(**variables)
        except TemplateError as e:
            logger.error("[PromptRegistry] Jinja2 render error for '{}': {}", key, e)
            raise
    return template_text


def get_chat_prompt(key: str, version: str | None = None, **variables) -> list[dict]:
    """加载多消息 prompt（system + human），返回 LangChain 消息列表格式。

    Args:
        key: 如 "supervisor/classify"，YAML 中应含 system 和 human 子键

    Returns:
        [{"role": "system", "content": "..."}, {"role": "human", "content": "..."}]
    """
    filename, name = key.split("/", 1)
    data = _load_yaml(f"{filename}.yaml")
    entry = data.get("prompts", {}).get(name)
    if entry is None:
        raise KeyError(f"Prompt '{key}' not found")

    messages = []
    for role in ("system", "human"):
        text = entry.get(role) if isinstance(entry, dict) else None
        if text is None:
            continue
        if variables:
            template = _jinja_env.from_string(text)
            text = template.render(**variables)
        messages.append({"role": role, "content": text})

    return messages
