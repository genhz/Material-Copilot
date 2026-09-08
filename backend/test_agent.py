"""
测试脚本 - 验证 LangChain Agent 功能
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from agent import execute_agent


async def test_chat_intent():
    """测试 CHAT 意图 - 概念性问题"""
    print("=" * 50)
    print("测试 1: CHAT 意图 - 什么是带隙？")
    print("=" * 50)

    result = await execute_agent(
        message="什么是带隙？请用通俗的语言解释。",
        history=[]
    )

    print(f"Action: {result.action}")
    print(f"Reply: {result.reply[:200]}...")
    print()


async def test_render_intent():
    """测试 RENDER 意图 - 查询材料结构"""
    print("=" * 50)
    print("测试 2: RENDER 意图 - 查询 Nd2Fe14B 晶体结构")
    print("=" * 50)

    result = await execute_agent(
        message="显示 Nd2Fe14B 的晶体结构",
        history=[]
    )

    print(f"Action: {result.action}")
    print(f"Reply: {result.reply[:200]}...")
    if result.material_data:
        print(f"Material: {result.material_data.formula} ({result.material_data.material_id})")
    print()


async def test_formula_only():
    """测试仅输入化学式"""
    print("=" * 50)
    print("测试 3: 仅输入化学式 Fe3O4")
    print("=" * 50)

    result = await execute_agent(
        message="Fe3O4",
        history=[]
    )

    print(f"Action: {result.action}")
    print(f"Reply: {result.reply[:200]}...")
    if result.material_data:
        print(f"Material: {result.material_data.formula} ({result.material_data.material_id})")
    print()


async def test_material_recommendation():
    """测试材料推荐"""
    print("=" * 50)
    print("测试 4: 材料推荐 - 哪些材料适合做永磁体？")
    print("=" * 50)

    result = await execute_agent(
        message="哪些材料适合做永磁体？",
        history=[]
    )

    print(f"Action: {result.action}")
    print(f"Reply: {result.reply[:200]}...")
    print()


async def main():
    """运行所有测试"""
    print("\n🧪 LangChain Agent 测试开始\n")

    # 测试 1: CHAT 意图
    await test_chat_intent()

    # 测试 2: RENDER 意图
    await test_render_intent()

    # 测试 3: 仅化学式
    await test_formula_only()

    # 测试 4: 材料推荐
    await test_material_recommendation()

    print("\n✅ 测试完成\n")


if __name__ == "__main__":
    asyncio.run(main())
