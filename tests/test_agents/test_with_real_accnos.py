"""
测试SQL Agent - 使用数据库中真实存在的AccNo
"""

import asyncio
import sys
import os
import uuid

sys.path.insert(0, '/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2')

TEST_EXCEL = "/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2/tests/test_agents/真实数据测试.xlsx"
CACHE_DIR = "/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2/cache/sql_analysis"


async def test_with_real_accnos():
    """使用真实AccNo测试"""
    print("=" * 80)
    print("测试: SQL Agent（使用数据库中真实存在的AccNo）")
    print("=" * 80)

    from agents.sql_analysis_agent import SQLAnalysisAgent
    import pandas as pd
    import shutil

    # 1. 检查测试文件
    print("\n[1] 检查测试文件...")
    if not os.path.exists(TEST_EXCEL):
        print(f"  ✗ 测试文件不存在: {TEST_EXCEL}")
        return False

    df_test = pd.read_excel(TEST_EXCEL)
    accnos = df_test['AccNo'].tolist()
    print(f"  ✓ 测试文件: {TEST_EXCEL}")
    print(f"  ✓ 行数: {len(df_test)}")
    print(f"  ✓ AccNo列表: {accnos}")

    # 2. 准备上传文件
    print("\n[2] 准备文件...")
    os.makedirs(CACHE_DIR, exist_ok=True)
    uploaded_file = os.path.join(CACHE_DIR, f"real_test_{uuid.uuid4().hex[:8]}.xlsx")
    shutil.copy(TEST_EXCEL, uploaded_file)
    print(f"  ✓ 文件: {uploaded_file}")

    # 3. 调用Agent
    print("\n[3] 调用SQL Analysis Agent...")

    question = f"""查询Excel中AccNo对应的真实检查时间和报告结论。

需要关联查询数据库：
- tRegorder表的AccNo（检查号）、CurPatientName（患者姓名）
- tRegProcedure表的ExamineDt（检查时间）
- tReport表的WYGText（报告结论）、WYSText（报告描述）
- 通过OrderGuid和ReportGuid关联

Excel文件路径: {uploaded_file}
原始文件名: 真实数据测试.xlsx

使用AccNo作为关联字段，将数据库查询结果合并到Excel并保存。"""

    agent = SQLAnalysisAgent()
    session_id = f"real_test_{uuid.uuid4().hex[:8]}"

    output_file = None
    df_db_rows = 0

    async for event in agent.analyze(question, session_id):
        event_type = event.get('type')

        if event_type == 'plan':
            print(f"\n  [执行计划] {event.get('data', {}).get('steps_count', 0)}个步骤")

        elif event_type == 'step_complete':
            data = event.get('data', {})
            status = "✓" if data.get('status') == 'success' else "✗"
            step_id = data.get('step_id', '?')
            row_count = data.get('row_count', 0)
            exec_time = data.get('execution_time_ms', 0) or 0
            print(f"  [{status}] Step {step_id}: {row_count}行, {exec_time:.0f}ms")

            if step_id == '2':  # 数据库查询步骤
                df_db_rows = row_count

            if data.get('error_message'):
                print(f"      错误: {data.get('error_message')[:200]}")

        elif event_type == 'final':
            final_data = event.get('data', {})
            print(f"\n  [最终结果]")
            print(f"    状态: {final_data.get('status')}")
            print(f"    总行数: {final_data.get('row_count', 0)}")
            output_file = final_data.get('output_file', '')

    # 4. 验证结果
    print("\n[4] 验证结果...")
    if output_file and os.path.exists(output_file):
        df_result = pd.read_excel(output_file)
        print(f"  ✓ 输出文件: {output_file}")
        print(f"  数据行数: {len(df_result)}")
        print(f"  数据列名: {df_result.columns.tolist()}")

        # 统计有效数据
        valid_counts = {}
        for col in ['WYSText', 'WYGText', '检查时间', 'CurPatientName']:
            if col in df_result.columns:
                valid_counts[col] = df_result[col].notna().sum()

        print("\n  有效数据统计:")
        for col, count in valid_counts.items():
            print(f"    {col}: {count}/{len(df_result)}")

        if df_db_rows > 0:
            print(f"\n  ✓ 成功！数据库查询返回 {df_db_rows} 行数据")
            print("\n  有数据的行预览:")
            has_data = df_result[df_result['WYSText'].notna() | df_result['WYGText'].notna()]
            if len(has_data) > 0:
                print(has_data[['AccNo', 'WYSText', 'WYGText']].head(3).to_string())
            return True
        else:
            print(f"\n  ✗ 数据库查询返回 0 行")
            return False
    else:
        print(f"  ✗ 输出文件不存在")
        return False


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("SQL Agent 真实AccNo测试")
    print("=" * 80)

    success = await test_with_real_accnos()

    print("\n" + "=" * 80)
    if success:
        print("✓ 测试通过！SQL Agent成功查询到真实数据。")
    else:
        print("✗ 测试失败")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
