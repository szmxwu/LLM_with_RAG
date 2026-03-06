"""
测试 deep_think 模式 - 验证 long_think 逻辑是否生效
"""
import asyncio
import aiohttp


async def test_deep_think():
    """测试深度思考模式"""
    print("=" * 60)
    print("测试 deep_think 模式（long_think 逻辑）")
    print("=" * 60)

    url = "http://localhost:6082/v2/ask"

    # 复杂问题，应该触发问题拆分
    payload = {
        "question": "肝癌的影像学表现、诊断标准和治疗方案是什么？",
        "dataset": "放射学",
        "user_id": "test-deep-think-001",
        "thinking_mode": "deep_think"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print(f"\n状态码: {response.status}\n")

                content = ""
                current_stage = None
                section_count = 0

                async for chunk in response.content.iter_chunked(1024):
                    if chunk:
                        text = chunk.decode('utf-8')
                        content += text

                        # 检测阶段标记
                        if "[STAGE:answer]" in text or "## 您的问题:" in text:
                            current_stage = "answer"
                            section_count += 1
                            if section_count == 1:
                                print("\n" + "=" * 40)
                                print("阶段1: 深度思考 - 问题拆分")
                                print("=" * 40)
                        elif "思考过程:" in text:
                            print("\n[思考过程输出...]")
                        elif "## 总结" in text:
                            print("\n" + "=" * 40)
                            print("阶段: 总结")
                            print("=" * 40)
                        elif "[STAGE:references]" in text:
                            current_stage = "references"
                            print("\n" + "=" * 40)
                            print("阶段: 参考文献")
                            print("=" * 40)
                        elif "[STAGE:keywords]" in text:
                            current_stage = "keywords"
                            print("\n" + "=" * 40)
                            print("阶段: 病例检索关键词")
                            print("=" * 40)
                        elif "[STAGE:complete]" in text:
                            current_stage = "complete"
                            print("\n" + "=" * 40)
                            print("全部完成")
                            print("=" * 40)

                        # 打印内容（限制长度）
                        if current_stage == "answer" and len(text) < 500:
                            print(text, end="")
                        elif current_stage in ["references", "keywords"]:
                            print(text[:200], end="")

                print("\n\n" + "=" * 60)
                print("测试完成!")
                print("=" * 60)

                # 检查结果是否包含深度思考特征
                if "## 您的问题:" in content:
                    print("\n✅ 检测到深度思考输出格式（包含'## 您的问题'）")
                if "思考过程:" in content:
                    print("✅ 检测到思考过程")
                if "## 总结" in content:
                    print("✅ 检测到总结部分")
                if "### 参考文献" in content:
                    print("✅ 检测到参考文献")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_standard_think():
    """测试标准模式（对比）"""
    print("\n\n" + "=" * 60)
    print("测试 think 模式（标准流程 - 对比）")
    print("=" * 60)

    url = "http://localhost:6082/v2/ask"

    payload = {
        "question": "肝癌的影像学表现有哪些？",
        "dataset": "放射学",
        "user_id": "test-think-001",
        "thinking_mode": "think"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print(f"\n状态码: {response.status}\n")

                content = ""
                char_count = 0

                async for chunk in response.content.iter_chunked(1024):
                    if chunk:
                        text = chunk.decode('utf-8')
                        content += text
                        char_count += len(text)

                print(f"收到 {char_count} 字符")

                if "## 您的问题:" in content:
                    print("❌ 错误：标准模式不应该有'## 您的问题'")
                else:
                    print("✅ 标准模式输出正确（无深度思考标记）")

                if "### 参考文献" in content:
                    print("✅ 包含参考文献")

    except Exception as e:
        print(f"测试失败: {e}")


if __name__ == "__main__":
    # 运行两个测试
    asyncio.run(test_deep_think())
    asyncio.run(test_standard_think())
