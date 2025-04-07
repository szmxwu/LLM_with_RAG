请根据以下需求生成一个SQL Server查询语句：
## 需求:
- {content}

## 数据库信息:
### 医生表（t_user）
t_user记录医生身份信息。以下是该表中每个字段的含义：
- `UserIdentity`: 整数类型，作为医生的唯一标识符。
- `UserName`: 字符串类型，用于存储医生的中文名字。
- `UserID`: 字符串类型，用于存储用户的登录名，由英文和数字组成。

### 检查流程表（t_order）
t_order记录患者在检查过程中的相关信息。以下是该表中每个字段的含义：
- `PatientIdentity`: 整数类型，作为患者的唯一标识符，与t_patient表的PatientIdentity字段相关联。
- `AccessionNumber`: 字符串类型，检查流水号，作为每次检查的唯一标识符。
- `TotalFee`: 浮点类型，代表每次检查的总费用或者医院收入。
- `AppliedDepartment`: 字符串类型，代表发起检查申请的科室名称。
- `PatientType`: 字符串类型，代表患者类型，包括[住院,门诊,急诊,体检,绿色通道]五种类型。	
- `ReportIdentity`: 整数类型，代表检查报告的唯一标识符，与t_report表的ReportIdentity字段相关联。
- `Bodyparts`: 字符串类型，代表检查的部位项目名称。
- `ModalityTypes`: 字符串类型，代表检查的设备类型名称，包括[DR,CT,MR,MG]四种类型。
- `SequenceNo`: 字符串类型，代表执行检查的具体机器名称，由设备类型+数字组成，例如DR01,CT04。
- `OrderCreateDate`: 时间戳类型，代表检查申请单开具的时间。
- `UpdateDateTime`: 时间戳类型，代表患者进行检查的时间。

### 检查报告表（t_report）
t_report记录患者检查报告的相关信息。以下是该表中每个字段的含义：
- `ReportIdentity`: 整数类型，作为患者的唯一标识符，与t_order表的ReportIdentity字段相关联。
- `Finding`: 字符串类型，代表检查报告中的描述内容。
- `Diagnose`: 字符串类型，代表检查报告中的结论内容。
- `Positive`: 整数类型，取值为0或者1，0代表阴性报告，1代表阳性报告
- `ImageQuality`: 整数类型，代表与报告对应的医学图像的质量
- `ReportQuality`: 整数类型，代表报告的书写质量  
- `Appover`: 整数类型，作为审核医生的唯一标识符，与t_user表的UserIdentity字段相关联。
- `Reporter`: 整数类型，作为报告医生或初诊医生的唯一标识符，与t_user表的UserIdentity字段相关联。
- `ReAppover`: 整数类型，作为复审医生（对审核医生再次审核）的唯一标识符，与t_user表的UserIdentity字段相关联。
- `ReportTime`: 时间戳类型，代表报告医生或初诊医生提交检查报告的时间。
- `AppoveTime`: 时间戳类型，代表审核医生提交检查报告的时间。
- `ReAppoveTime`: 时间戳类型，代表复审医生提交检查报告的时间。
  
### 患者信息表（t_patient）
t_patient记录患者个人信息。以下是该表中每个字段的含义：
- `PatientIdentity`: 整数类型，作为患者的唯一标识符，与t_order表的PatientIdentity字段相关联。
- `PatientID`: 字符串类型，代表患者的检查号码，非唯一值。
- `PatientName`: 字符串类型，代表患者中文名字。
- `PatientNameEn`: 字符串类型，代表患者英文名字。
- `IdentityCardNumber`: 字符串类型，代表患者身份证号码。
- `PatientGender`: 字符串类型，代表患者性别，包括[男,女]两种类型。
- `BirthDate`: 时间戳类型，代表患者生日。
- `Telephone`: 字符串类型，代表患者电话号码。
- `UPID`: 整数类型，代表患者唯一主索引号。

## 生成SQL的步骤：
1. **判断需求有效性**:判断用户的提问是否与本数据库的SQL有关，如果无关，请返回"无法生成SQL" ，不再执行后续步骤。
2. **解析需求**: 一步一步思考，你首先解析用户需求，判断哪些字段是需要用到的，然后再为每个字段设定条件。
3. **检查时间范围**: 
   - 必须避免对整个表进行查询！如果需求没有提到时间条件，默认添加最近一个月的检查时间范围 (检查时间字段为`t_order.UpdateDateTime`)。
4. **检查设备类型**: 
   - 如果需求中涉及检查设备类型 (`ModalityTypes`)，为其设置对应的条件。
   - 如果未涉及设备类型，默认条件为 `ModalityTypes IN ('CT', 'DX', 'MR', 'MG')`。
5. **模糊查询**: 
   - 如果需求中涉及 `AppliedDepartment`、`Finding` 或 `Diagnose`，则使用模糊查询 (`LIKE`);其他字段则使用精确查询(`=`)
6. **排除无关字段**: 
   - 不要在查询中包含与需求无关的字段。
7. **限制查询记录数量**:
   - 为了避免SQL服务器过载，你需要限制select 查询返回的记录数量不大于1000条，为其添加 top 1000。
   
## 输出格式：
- 输出符合MS SQL SERVER语法的SQL语句，请务必不要使用mysql的语法，例如limit
- 直接输出SQL语句，不要解释，不要评论