"""
子进程SQL执行器
在隔离的Python进程中执行SQL查询，确保TLS配置正确
"""
import os
import sys
import json
import tempfile

# 必须在导入pyodbc/sqlalchemy之前设置OPENSSL_CONF
openssl_config = """# OpenSSL配置允许遗留算法
openssl_conf = default_conf
[default_conf]
ssl_conf = ssl_sect
[ssl_sect]
system_default = system_default_sect
[system_default_sect]
CipherString = DEFAULT:@SECLEVEL=0
"""
config_path = os.path.join(tempfile.gettempdir(), 'openssl-legacy.cnf')
with open(config_path, 'w') as f:
    f.write(openssl_config)
os.environ['OPENSSL_CONF'] = config_path

# 现在导入其他模块
import pandas as pd
import sqlalchemy as sql
from sqlalchemy import text


def execute_sql(connection_string, query):
    """执行SQL查询并返回结果"""
    try:
        engine = sql.create_engine(connection_string)
        df = pd.read_sql(query, engine)
        return {
            'success': True,
            'data': df.to_dict(orient='records'),
            'columns': df.columns.tolist(),
            'row_count': len(df)
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__
        }


if __name__ == '__main__':
    # 从命令行参数读取配置
    if len(sys.argv) < 3:
        print(json.dumps({'success': False, 'error': '参数不足'}))
        sys.exit(1)

    connection_string = sys.argv[1]
    query = sys.argv[2]

    result = execute_sql(connection_string, query)
    print(json.dumps(result, default=str))
