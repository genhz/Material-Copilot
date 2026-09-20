"""
调试 Agent 消息类型
"""
import asyncio
import json
from agent import get_agent

async def debug_messages():
    """调试 Agent 返回的消息"""
    print("=" * 50)
    print("调试：材料搜索 - '查询 Nd2Fe14B 的晶体结构'")
    print("=" * 50)

    agent = get_agent()

    # 执行 Agent
    result = await agent.agent.ainvoke({
        "messages": [
            {"role": "user", "content": "查询 Nd2Fe14B 的晶体结构"},
        ]
    })

    # 打印所有消息
    output_messages = result.get("messages", [])
    print(f"\n消息数量：{len(output_messages)}\n")

    for i, msg in enumerate(output_messages):
        msg_type = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", "")
        name = getattr(msg, "name", None)
        tool_call_id = getattr(msg, "tool_call_id", None)
        tool_calls = getattr(msg, "tool_calls", None)

        print(f"--- 消息 {i} ---")
        print(f"type: {msg_type}")
        print(f"name: {name}")
        print(f"tool_call_id: {tool_call_id}")
        print(f"tool_calls: {tool_calls}")
        if msg_type == "tool":
            print(f"content (JSON): {content[:200] if content else 'None'}...")
        else:
            print(f"content: {content[:200] if content else 'None'}...")
        print()

if __name__ == "__main__":
    asyncio.run(debug_messages())
