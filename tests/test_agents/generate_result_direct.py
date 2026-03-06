"""
直接生成结果Excel文件 - 不使用LLM，手动编写SQL
"""

import sys
sys.path.insert(0, '/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2')

import pandas as pd
import subprocess
import json
import os
from datetime import datetime

from config.settings import settings

# 路径配置
TEST_EXCEL = "/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2/tests/test_agents/放射科退费.xlsx"
CACHE_DIR = "/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2/cache/sql_analysis"
OUTPUT_FILE = os.path.join(CACHE_DIR, f"最终结果_{datetime.now().strftime('%m%d_%H%M%S')}.xlsx")

def execute_sql(sql, timeout=60):
    """执行SQL查询"""
    result = subprocess.run(
        ['python', '/home/wmx/work/python/LLM_with_RAG/LLM_with_RAG_v2/sql_executor_subprocess.py',
         settings.odbc_connection, sql],
        capture_output=True, text=True, timeout=timeout
    )
    try:
        return json.loads(result.stdout)
    except:
        print(f"SQL执行错误: {result.stdout[:500]}")
        return {'success': False, 'error': '解析失败'}

def main():
    print("=" * 80)
    print("直接生成结果Excel文件")
    print("=" * 80)

    # 1. 读取Excel
    print("\n[1] 读取Excel文件...")
    df_excel = pd.read_excel(TEST_EXCEL)
    print(f"  ✓ 总行数: {len(df_excel)}")
    print(f"  ✓ 列名: {df_excel.columns.tolist()}")

    # 2. 获取所有AccNo（去重）
    print("\n[2] 提取AccNo列表...")
    accnos = df_excel['AccNo'].dropna().unique().tolist()
    print(f"  ✓ 唯一AccNo数量: {len(accnos)}")

    # 3. 分批查询数据库（避免SQL过长）
    print("\n[3] 查询数据库...")
    all_results = []
    batch_size = 200  # 每批200个AccNo

    for i in range(0, len(accnos), batch_size):
        batch = accnos[i:i+batch_size]
        accnos_str = ', '.join([f"'{a}'" for a in batch])

        print(f"  查询批次 {i//batch_size + 1}/{(len(accnos)-1)//batch_size + 1} ({len(batch)}个AccNo)...")

        # 手动编写SQL - 使用LEFT JOIN确保保留所有AccNo
        sql = f"""
        SELECT
            ro.AccNo,
            ro.CurPatientName AS 患者姓名,
            rp.ExamineDt AS 检查时间,
            r.WYSText AS 报告描述,
            r.WYGText AS 报告结论,
            r.CreateDt AS 报告时间
        FROM tRegorder ro
        LEFT JOIN tRegProcedure rp ON ro.OrderGuid = rp.OrderGuid
        LEFT JOIN tReport r ON rp.ReportGuid = r.ReportGuid
        WHERE ro.AccNo IN ({accnos_str})
        """

        result = execute_sql(sql)

        if result.get('success'):
            batch_df = pd.DataFrame(result['data'])
            if not batch_df.empty:
                # 如果同一AccNo有多行（多个检查部位），取有报告的第一条
                batch_df = batch_df.drop_duplicates(subset=['AccNo'], keep='first')
                all_results.append(batch_df)
                print(f"    ✓ 返回 {len(batch_df)} 行")
            else:
                print(f"    ○ 无数据")
        else:
            print(f"    ✗ 查询失败: {result.get('error', '未知错误')[:100]}")

    # 4. 合并查询结果
    print("\n[4] 合并数据...")
    if all_results:
        df_db = pd.concat(all_results, ignore_index=True)
        # 再次去重
        df_db = df_db.drop_duplicates(subset=['AccNo'], keep='first')
        print(f"  ✓ 数据库查询总计: {len(df_db)} 行")
        print(f"  ✓ 有报告的数据: {df_db['报告结论'].notna().sum()} 行")
    else:
        df_db = pd.DataFrame()
        print(f"  ⚠ 数据库无返回数据")

    # 5. 合并Excel和数据库结果（LEFT JOIN保留所有Excel行）
    print("\n[5] 合并Excel和数据库结果...")
    if not df_db.empty:
        df_merged = df_excel.merge(df_db, on='AccNo', how='left')
    else:
        df_merged = df_excel.copy()
        df_merged['患者姓名'] = None
        df_merged['检查时间'] = None
        df_merged['报告描述'] = None
        df_merged['报告结论'] = None
        df_merged['报告时间'] = None

    print(f"  ✓ 合并后总行数: {len(df_merged)}")

    # 6. 统计有效数据
    print("\n[6] 数据统计:")
    new_columns = ['患者姓名', '检查时间', '报告描述', '报告结论', '报告时间']
    for col in new_columns:
        if col in df_merged.columns:
            valid_count = df_merged[col].notna().sum()
            print(f"  {col}: {valid_count}/{len(df_merged)} ({valid_count/len(df_merged)*100:.1f}%)")

    # 7. 保存结果
    print("\n[7] 保存结果文件...")
    os.makedirs(CACHE_DIR, exist_ok=True)
    df_merged.to_excel(OUTPUT_FILE, index=False)
    print(f"  ✓ 文件已保存: {OUTPUT_FILE}")
    print(f"  ✓ 文件大小: {os.path.getsize(OUTPUT_FILE)} bytes")

    # 8. 显示样本数据
    print("\n[8] 有报告数据的样本:")
    has_report = df_merged[df_merged['报告结论'].notna()]
    print(f"  共 {len(has_report)} 行有报告数据")
    if len(has_report) > 0:
        print("\n  前5行预览:")
        display_cols = ['AccNo', '病人姓名', '操作工号', '金额', '报告结论']
        available_cols = [c for c in display_cols if c in df_merged.columns]
        print(has_report[available_cols].head().to_string())

    print("\n" + "=" * 80)
    print("完成！")
    print(f"输出文件: {OUTPUT_FILE}")
    print("=" * 80)

if __name__ == "__main__":
    main()
