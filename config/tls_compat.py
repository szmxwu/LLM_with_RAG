"""
TLS兼容性自动配置模块

解决OpenSSL 3.0与旧版SQL Server (如SQL Server 2012)的TLS兼容性问题
在应用启动时自动检测并配置环境
"""
import os
import sys
import tempfile
import logging

# 关键：首先加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv未安装，跳过

logger = logging.getLogger(__name__)

# OpenSSL遗留算法配置文件内容
OPENSSL_LEGACY_CONFIG = """# OpenSSL配置允许遗留算法
# 用于解决OpenSSL 3.0与SQL Server 2012的TLS兼容性问题
openssl_conf = default_conf

[default_conf]
ssl_conf = ssl_sect

[ssl_sect]
system_default = system_default_sect

[system_default_sect]
CipherString = DEFAULT:@SECLEVEL=0
"""


def check_openssl_version():
    """检测OpenSSL版本"""
    try:
        import ssl
        openssl_version = ssl.OPENSSL_VERSION
        logger.info(f"OpenSSL版本: {openssl_version}")

        # 解析版本号
        version_parts = openssl_version.split()
        for part in version_parts:
            if part[0].isdigit():
                major_version = int(part.split('.')[0])
                return major_version
        return None
    except Exception as e:
        logger.warning(f"无法检测OpenSSL版本: {e}")
        return None


def is_sql_server_connection_used():
    """检测是否配置了SQL Server连接"""
    odbc_str = os.getenv('ODBC', '')
    return 'mssql' in odbc_str.lower() or 'sql' in odbc_str.lower()


def create_openssl_config_file():
    """创建OpenSSL配置文件"""
    try:
        # 检查是否已存在配置文件
        config_path = os.environ.get('OPENSSL_CONF')
        if config_path and os.path.exists(config_path):
            logger.info(f"使用现有的OpenSSL配置: {config_path}")
            return config_path

        # 创建临时配置文件
        config_path = os.path.join(tempfile.gettempdir(), 'openssl-legacy.cnf')
        with open(config_path, 'w') as f:
            f.write(OPENSSL_LEGACY_CONFIG)

        logger.info(f"创建OpenSSL配置文件: {config_path}")
        return config_path

    except Exception as e:
        logger.error(f"创建OpenSSL配置文件失败: {e}")
        return None


def _patch_ssl_context():
    """
    修补SSLContext以允许遗留算法
    在OpenSSL 3.0+中，SECLEVEL=2会禁用SHA1等算法，导致SQL Server 2012连接失败
    """
    try:
        import ssl
        # 获取默认SSL上下文并降低安全级别
        context = ssl.create_default_context()
        # 设置密码字符串允许遗留算法
        context.set_ciphers('DEFAULT:@SECLEVEL=0')
        # 保存原始函数
        if not hasattr(ssl, '_create_default_context_orig'):
            ssl._create_default_context_orig = ssl.create_default_context
            ssl._create_stdlib_context_orig = ssl._create_stdlib_context

            def _create_default_context_patched(*args, **kwargs):
                ctx = ssl._create_default_context_orig(*args, **kwargs)
                ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
                return ctx

            def _create_stdlib_context_patched(*args, **kwargs):
                ctx = ssl._create_stdlib_context_orig(*args, **kwargs)
                ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
                return ctx

            ssl.create_default_context = _create_default_context_patched
            ssl._create_stdlib_context = _create_stdlib_context_patched
            logger.info("已修补SSLContext以允许遗留算法")
        return True
    except Exception as e:
        logger.warning(f"修补SSLContext失败: {e}")
        return False


def configure_tls_compatibility():
    """
    自动配置TLS兼容性
    在导入任何数据库相关模块之前调用
    """
    # 检测OpenSSL版本
    openssl_major = check_openssl_version()
    if openssl_major is None:
        logger.warning("无法检测OpenSSL版本，跳过TLS兼容性配置")
        return False

    # 只有当OpenSSL版本 >= 3.0 且使用SQL Server时才需要配置
    if openssl_major < 3:
        logger.info(f"OpenSSL版本 {openssl_major} < 3.0，不需要兼容性配置")
        return True

    if not is_sql_server_connection_used():
        logger.info("未检测到SQL Server连接配置，跳过TLS兼容性配置")
        return True

    # 方法1: 设置OPENSSL_CONF环境变量
    config_path = create_openssl_config_file()
    if config_path:
        os.environ['OPENSSL_CONF'] = config_path
        logger.info(f"已设置OPENSSL_CONF={config_path}")

    # 方法2: 直接修补SSLContext（更可靠）
    _patch_ssl_context()

    # 方法3: 设置Python SSL默认密码套件
    try:
        import ssl
        ssl._DEFAULT_CIPHERS = 'DEFAULT:@SECLEVEL=0'
    except Exception as e:
        logger.warning(f"设置默认密码套件失败: {e}")

    # logger.warning(
    #     "注意: 已启用OpenSSL遗留算法以兼容SQL Server 2012。"
    #     "这在内部网络环境中是安全的。"
    # )
    return True


def test_sql_connection():
    """测试SQL Server连接"""
    try:
        import sqlalchemy as sql
        from sqlalchemy import text

        odbc_str = os.getenv('ODBC')
        if not odbc_str:
            logger.warning("未找到ODBC连接字符串")
            return False

        engine = sql.create_engine(odbc_str)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT @@VERSION AS version"))
            version = result.fetchone()[0]
            logger.info(f"数据库连接成功: {version[:50]}...")
            return True

    except Exception as e:
        logger.error(f"数据库连接测试失败: {e}")
        return False


def setup():
    """
    设置TLS兼容性（主入口函数）
    在应用启动时调用
    """
    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 配置TLS兼容性
    if configure_tls_compatibility():
        # 如果配置了兼容性，测试连接
        if is_sql_server_connection_used():
            logger.info("正在测试SQL Server连接...")
            if test_sql_connection():
                logger.info("✅ SQL Server连接正常")
            else:
                logger.error("❌ SQL Server连接失败")
    else:
        logger.warning("TLS兼容性配置未完成")


# 向后兼容的别名
auto_configure_tls = configure_tls_compatibility

if __name__ == "__main__":
    setup()
