import json
prompt_str = """
请根据以下需求生成一个SQL Server查询语句：

### 数据库信息:
- **表名:** `tAllReportInfo`
- **字段:**
  - HISPID (varchar, 主键): 患者ID
  - ClinicNo (varchar): 门诊号
  - InhospitalNo (varchar): 住院号
  - RISPID (varchar): 检查号
  - PatientType (varchar): 患者类型或病人类别 ('门诊', '住院', '急诊', '体检')
  - AccessionNumber (varchar): 影像号
  - PatientCName (varchar): 姓名
  - BirthDay (date): 生日
  - Sex (varchar): 性别
  - IDNo (varchar): 身份证号码
  - ApplyDeptName (varchar): 申请科室
  - ProcedureDesc (varchar): 检查部位
  - ModalityType (varchar): 检查设备类型 ('CT', 'DR', 'MR', 'MG','ES','PS','US')
  - ModalityName (varchar): 检查设备机器名称
  - Technician (varchar): 技师姓名
  - ReportDoctor (varchar): 报告医生姓名
  - ReportApprover (varchar): 审核医生姓名
  - StudyDateTime (datetime): 检查时间
  - Representation (varchar): 报告描述
  - Impression (varchar): 报告结论
  - Charge (float): 检查费用
  - IsPositive (varchar):是否阳性("阳性","未指定")

### 需求:
- {content}

### 生成SQL的步骤：
1. **判断需求有效性**:判断用户的提问是否与生成SQL有关，如果无关，请直接回复用户的信息 ，不再执行后续步骤。
2. **解析需求**: 一步一步思考，你首先解析用户需求，判断哪些字段是需要用到的，然后再为每个字段设定条件。
3. **检查时间范围**: 
   - 如果需求没有提到时间条件，默认添加最近一个月的检查时间范围 (`StudyDateTime`)。
4. **检查设备类型**: 
   - 如果需求中涉及检查设备类型 (`ModalityType`)，为其设置对应的条件。
   - 如果未涉及设备类型，默认条件为 `ModalityType IN ('CT', 'DR', 'MR', 'MG')`。
5. **模糊查询**: 
   - 如果需求中涉及 `ApplyDeptName`、`Impression` 或 `Representation`，则使用模糊查询 (`LIKE`)。
   - 如果与这些字段无关，则无需查询这些字段。
6. **检查设备机器名称**: 
   - 如果需求中未指定 `ModalityName`，则添加条件: `ModalityName NOT LIKE 'LH%'`。
7. **排除无关字段**: 
   - 不要在查询中包含与需求无关的字段。

### 输出格式：
- 输出符合SQL SERVER语法的SQL语句，请务必不要使用mysql的语法，例如limit

### 示例:
{examples}

"""
prompt_file = {
    "_type": "prompt",
    "input_variables": ["content","examples"],
    "template": prompt_str}
with open('prompt/sql_prompt.json', 'w', encoding='utf-8') as f:
    f.write(json.dumps(prompt_file, ensure_ascii=False))
