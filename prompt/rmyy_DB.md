请根据以下需求生成一个SQL Server查询语句：
## 需求:
- ""

## 数据库信息:
### 医生表(tUser)
tUser记录医生身份信息。以下是该表中每个字段的含义：
- `UserGuid`: 字符串类型，代表医生的全局唯一标识符（GUID），与tReport表的`FirstApprover`或`Submitter`字段相关联，与tRegProcedure表的`Technician`字段相关联
- `DisplayName`: 字符串类型，用于存储医生的中文名字。
- `LoginName`: 字符串类型，用于存储用户的登录名，由英文和数字组成

### 检查信息表(tRegorder)
tRegorder记录患者检查的基本信息。以下是该表中每个字段的含义：
- `AccNo`: 字符串类型，检查流水号，作为每次检查的唯一标识符
- `CurPatientName`: 字符串类型，代表患者中文名字。
- `CurGender`: 字符串类型，代表患者性别，包括[男,女]两种类型。
- `ApplyDept`: 字符串类型，代表发起检查申请的科室名称
- `InhospitalNo`: 字符串类型，代表住院患者的住院号，非住院患者为空
- `ClinicNo`: 字符串类型，代表门诊患者的门诊号，非门诊患者为空
- `OrderGuid`: 字符串类型，代表检查信息的全局唯一标识符（GUID），与tRegProcedure表的OrderGuid字段相关联
- `PatientType`: 字符串类型，代表患者类型，包括[住院,门诊,门诊急诊,住院急诊,体检,绿色通道]六种类型，其中[门诊急诊,住院急诊,绿色通道]属于急诊类型
- `Totalfee`: 浮点类型，代表每次检查的总费用或者医院收入
- `InternalOptional1`: 时间戳类型，代表患者的检查申请单开具的时间，简称申请时间。

### 检查流程表(tRegProcedure)
tRegProcedure记录患者在检查过程中的详细信息。以下是该表中每个字段的含义：
- `OrderGuid`: 字符串类型，代表检查信息的全局唯一标识符（GUID），与tRegorder表的OrderGuid字段相关联
- `ReportGuid`: 字符串类型，代表检查报告的全局唯一标识符（GUID），与tReport表的ReportGuid字段相关联
- `CheckingItem`: 字符串类型，代表检查的部位项目名称。
- `ModalityType`: 字符串类型，代表检查的设备类型名称，包括[DR,CT,MR,MG]四种类型。
- `Modality`: 字符串类型，代表执行检查的具体机器名称，由设备类型+数字组成，例如:DR01,CT04。
- `RegisterDt`: 时间戳类型，代表患者登记的时间
- `ExamineDt`: 时间戳类型，代表患者进行检查的时间
- `Technician`: 字符串类型，代表检查技术员或技师的全局唯一标识符（GUID），与tUser表的UserGuid字段相关联

### 检查报告表(tReport)
tReport记录患者检查报告的相关信息。以下是该表中每个字段的含义：
- `ReportGuid`: 字符串类型，代表检查报告的全局唯一标识符（GUID），与tRegProcedure表的ReportGuid字段相关联
- `WYSText`: 字符串类型，代表检查报告中的描述内容。
- `WYGText`: 字符串类型，代表检查报告中的结论内容。
- `IsPositive`: 整数类型，取值为0或者1，0代表阴性报告，1代表阳性报告
- `FirstApprover`: 字符串类型，代表审核医生的全局唯一标识符（GUID），与tUser表的UserGuid字段相关联
- `Submitter`: 字符串类型，代表报告医生的全局唯一标识符（GUID），与tUser表的UserGuid字段相关联
- `CreateDt`: 时间戳类型，代表报告医生或初诊医生提交检查报告的时间，简称报告时间。
- `FirstApproveDt`: 时间戳类型，代表审核医生提交检查报告的时间，检查审核时间。

### 患者信息表(tRegPatient)
tRegPatient记录患者个人信息。以下是该表中每个字段的含义：
- `PatientGuid`: 字符串类型，代表患者信息的全局唯一标识符（GUID），与tRegorder表的PatientGuid字段相关联
- `PatientID`: 字符串类型，代表患者的检查号码，非唯一值。
- `ReferenceNo`: 字符串类型，代表患者身份证号码。
- `BirthDay`: 时间戳类型，代表患者生日。
- `Telephone`: 字符串类型，代表患者电话号码。
- `RemotePID`: 字符串类型，代表患者唯一主索引号。

## 生成SQL的步骤：
1. **判断需求有效性**:判断用户的提问是否与本数据库的SQL有关，如果无关，请返回"无法生成SQL" ，不再执行后续步骤
2. **解析需求**: 一步一步思考，你首先解析用户需求，判断哪些字段是需要用到的，然后再为每个字段设定条件
3. **模糊查询**: 
   - 如果需求中涉及 `ApplyDept`、`WYSText` 或 `WYGText`，则使用模糊查询 (`LIKE`);其他字段则使用精确查询(`=`)
4. **检查设备机器名称**: 
   - 对于所有需求，你必须检查需求中是否指定了具体机器名称；如果没有指定，则添加默认条件: `tRegProcedure.Modality NOT LIKE 'LH%'`，并jion到tRegProcedure表
5. **区分检查部位数量和人次**:
   - 如果需求是统计人次，则需要对`AccNo`字段去重(DISTINCT AccNo)后作为总数或者分子；如果需求是统计部位，则无需去重
6. **时间差统计**:
   - 如果需求要求统计预约时间，预约时间=检查时间-申请时间，单位为天，仅保留0到60天的记录，仅包括`住院`和`门诊`两种类型的患者
   - 如果需求要求统计检查等待时间，等待时间=检查时间-预约时间，单位为分钟，仅保留0到120分钟的记录
7. **限制查询范围**:
   - 为了避免SQL服务器过载，必须避免对整个表进行查询！如果需求没有提到时间条件，请添加最近一个月的检查时间范围(`ExamineDt`)
   
## 输出格式：
- 输出符合MS SQL SERVER语法的SQL语句，请务必不要使用mysql的语法，例如limit
- 直接输出SQL语句，不要解释，不要评论
   