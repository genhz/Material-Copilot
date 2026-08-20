"""
技能模块 — 每个技能封装一个独立的能力
"""
from skills.material_search import search_material as material_search
from skills.chat import chat as chat_skill

__all__ = ["material_search", "chat_skill"]
