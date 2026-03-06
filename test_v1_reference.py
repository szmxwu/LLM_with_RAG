"""
测试 V1 版本的参考文献处理逻辑
验证 ans.reference 被正确处理
"""
import asyncio
import aiohttp


async def test_v1_reference_logic():
    """测试参考文献是否被正确处理"""
    print("=" * 60)
    print("测试 V1 参考文献处理逻辑")
    print("=" * 60)

    url = "http://localhost:6082/v2/ask"

    payload = {
        "question": "肝癌的影像学表现有哪些？",
        "dataset": "放射学",
        "user_id": "test-ref-001",
        "thinking_mode": "think"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print(f"\n状态码: {response.status}\n")

                content = ""
                has_references = False
                has_keywords = False

                async for chunk in response.content.iter_chunked(1024):
                    if chunk:
                        text = chunk.decode('utf-8')
                        content += text

                        if "[STAGE:references]" in text:
                            has_references = True
                            print("\n" + "=" * 40)
                            print("✅ 检测到参考文献阶段")
                            print("=" * 40)

                        if "[STAGE:keywords]" in text:
                            has_keywords = True
                            print("\n" + "=" * 40)
                            print("✅ 检测到关键词阶段")
                            print("=" * 40)

                print("\n" + "=" * 60)
                print("测试结果")
                print("=" * 60)

                if "### 参考文献" in content:
                    ref_count = content.count("[") - content.count("<[")
                    print(f"✅ 包含参考文献（约 {ref_count} 条）")
                else:
                    print("❌ 未检测到参考文献")

                if "相关病例图片" in content:
                    print("✅ 包含病例检索链接")
                else:
                    print("❌ 未检测到病例检索链接")

                # 检查是否包含引用标记
                if "##" in content and "$$" in content:
                    print("✅ 回答中包含引用标记 ##$$")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_v1_reference_logic())
