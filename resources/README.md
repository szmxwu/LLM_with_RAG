# 资源文件目录

本目录存放项目所需的配置和数据资源文件。

## 目录结构

```
resources/
├── config/                 # 配置文件
│   └── system_config.ini   # 系统配置（停用词、句式模式等）
│
└── dictionaries/           # 词典数据文件
    ├── match_replace.xlsx      # 文本清洗匹配替换规则
    ├── replace.xlsx            # 词汇替换词典
    └── 报告助手部位词典.xlsx    # 医学部位知识图谱（3个sheet）
```

## 文件说明

### config/system_config.ini
系统配置文件，包含：
- `sentence` 段落分割模式
- `clean` 文本清洗规则（停用词、标点、忽略关键词等）
- `positive` 阳性词配置
- `orientation` 方位词配置

### dictionaries/match_replace.xlsx
文本清洗用的匹配替换规则表，用于：
- 标准化医学术语
- 替换同义词
- 清理无用词汇

### dictionaries/replace.xlsx
词汇替换词典，用于：
- 诊断结果标准化
- 关键词统一替换

### dictionaries/报告助手部位词典.xlsx
医学部位知识图谱，包含3个sheet：
- **Sheet 0**: 部位知识图谱（分类、部位、子部位层级关系）
- **Sheet 1**: 标题知识图谱（用于标题部位识别）
- **Sheet 2**: 正常测量值（各部位正常参考值）

## 代码引用方式

```python
# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 资源目录
_CONFIG_DIR = os.path.join(_PROJECT_ROOT, 'resources', 'config')
_DICTIONARIES_DIR = os.path.join(_PROJECT_ROOT, 'resources', 'dictionaries')

# 读取配置
import configparser
conf = configparser.ConfigParser()
conf.read(os.path.join(_CONFIG_DIR, 'system_config.ini'), encoding='utf-8')

# 读取词典
import pandas as pd
df = pd.read_excel(os.path.join(_DICTIONARIES_DIR, '报告助手部位词典.xlsx'), sheet_name=0)
```

## 注意事项

1. 所有资源文件应使用 UTF-8 编码
2. Excel 文件应保持原有格式，不要修改表头
3. 修改配置后需要重启服务才能生效
4. 建议定期备份这些文件
