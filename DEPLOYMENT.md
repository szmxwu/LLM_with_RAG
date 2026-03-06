# LLM_with_RAG_v2 部署指南

## 系统要求

- Python >= 3.9
- Linux/macOS/Windows
- 至少 8GB RAM
- 网络访问权限（用于连接Xinference、RAGFlow和MSSQL）

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 到 `.env` 并修改配置：

```bash
cp .env.example .env
```

关键配置项：

```ini
# LLM配置（Xinference）
XINFERENCE=http://your-xinference-server:9997/v1
LLM_NAME=qwen3

# RAGFlow配置
BASE_URL=http://your-ragflow-server:9380
API_KEY=your-api-key

# 数据库配置（MSSQL）
ODBC=mssql+pyodbc://RIS:RIS@server\instance/GCRIS2?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=no&TrustServerCertificate=yes

# 安全配置
SECURITY_PASSWORD=your-secure-password
```

### 3. 启动服务

```bash
python main.py
```

或使用uvicorn：

```bash
uvicorn main:app --host 0.0.0.0 --port 6082 --reload
```

### 4. 访问API文档

浏览器访问：`http://localhost:6082/docs`

默认密码：`hK9#mP2$vL5&sN8*tB1!`（生产环境请务必修改）

---

## TLS兼容性自动配置

### 问题说明

OpenSSL 3.0+ 与 SQL Server 2012/2014 存在TLS兼容性问题，会导致连接失败：

```
SSL Provider: [error:0A00014D:SSL routines::legacy sigalg disallowed or unsupported]
```

### 自动解决方案

本项目已集成自动TLS兼容性配置，在 `main.py` 启动时会自动：

1. 检测OpenSSL版本（>=3.0才需要处理）
2. 检测是否配置了SQL Server连接
3. 自动创建并配置OpenSSL遗留算法配置文件
4. 设置环境变量 `OPENSSL_CONF`

**无需手动干预！**

### 手动配置（如需要）

如果需要在其他脚本中使用数据库连接，请确保：

```python
# 在导入任何数据库模块之前
from config.tls_compat import configure_tls_compatibility
configure_tls_compatibility()

# 然后正常使用SQLAlchemy
import sqlalchemy as sql
engine = sql.create_engine(os.getenv('ODBC'))
```

### 验证TLS配置

```bash
python config/tls_compat.py
```

---

## 离线部署

### 1. 准备依赖包

在有网络的环境中：

```bash
mkdir -p packages
pip download -r requirements.txt -d packages/
tar -czvf packages.tar.gz packages/
```

### 2. 离线安装

在目标服务器上：

```bash
tar -xzvf packages.tar.gz
pip install --no-index --find-links=packages -r requirements.txt
```

### 3. 安装系统依赖

**Ubuntu/Debian:**

```bash
sudo apt-get update
sudo apt-get install -y unixodbc unixodbc-dev
```

**CentOS/RHEL:**

```bash
sudo yum install -y unixODBC unixODBC-devel
```

### 4. 安装ODBC驱动

**Ubuntu/Debian:**

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

**验证驱动安装:**

```bash
python -c "import pyodbc; print(pyodbc.drivers())"
```

应输出：`['ODBC Driver 17 for SQL Server']`

---

## 常见问题

### Q1: 数据库连接超时

**检查项:**

1. 网络连通性：`ping 172.17.250.190`
2. 端口开放：`telnet 172.17.250.190 1433`
3. SQL Server服务状态
4. 防火墙设置

**测试连接:**

```bash
python test_db_connection.py
```

### Q2: LangChain版本不兼容

**错误示例:**

```
No module named 'langchain.prompts'
```

**解决方案:**

确保使用 `requirements.txt` 中固定的版本。如已安装其他版本：

```bash
pip install -r requirements.txt --force-reinstall
```

### Q3: 内存不足

**症状:** 启动时被OOM Killer终止

**解决方案:**

1. 增加物理内存
2. 或修改启动参数降低内存使用：

```bash
# 限制并发工作进程
uvicorn main:app --workers 1 --limit-concurrency 100
```

### Q4: SSL证书验证失败

如果连接到外部API时遇到SSL错误：

```bash
export SSL_VERIFY=false
```

或在 `.env` 中设置：

```ini
SSL_VERIFY=false
```

**注意:** 仅在内网可信环境中禁用SSL验证。

---

## 生产环境检查清单

- [ ] 修改默认密码 (`SECURITY_PASSWORD`)
- [ ] 禁用调试模式 (`DEBUG=false`)
- [ ] 配置HTTPS（使用反向代理如nginx）
- [ ] 启用防火墙，仅开放必要端口
- [ ] 配置日志轮转
- [ ] 设置监控告警
- [ ] 定期备份数据库

---

## 技术支持

遇到问题请检查：

1. 日志文件：`AgentServer.log`
2. 测试脚本：`test_db_connection.py`, `test_langchain_compat.py`
3. 配置文件：`.env`, `system_config.ini`
