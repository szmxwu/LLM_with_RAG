"""Prompt模板统一管理 - 支持思考强度控制"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from config.settings import ThinkingMode


@dataclass
class PromptTemplates:
    """Prompt模板集合 - 支持/no_think和/think指令控制思考强度"""

    # ==================== 思考指令常量 ====================
    # Qwen模型支持 /no_think 和 /think 指令

    NO_THINK_INSTRUCTION = """/no_think
请直接给出答案，不需要展示推理过程。保持回答简洁高效。
"""

    THINK_INSTRUCTION = """/think
请展示你的推理过程，然后给出答案。推理过程可以帮助理解结论。
"""

    DEEP_THINK_INSTRUCTION = """/think
请进行深度推理分析：
1. 首先全面分析问题的各个方面
2. 考虑多种可能性并进行对比
3. 逐步推导出结论
4. 最后给出经过深思熟虑的答案
请确保推理过程详尽、逻辑严密。
"""

    # ==================== 意图分析 Prompt ====================
    INTENT_ANALYSIS: str = """你是一个智能任务分析器。{thinking_instruction}

用户问题：{question}

请判断：
1. 是否需要使用医学知识库？
2. 任务复杂度级别？（simple/moderate/complex）
3. 如果需要工具调用，应该调用哪些工具？
4. 建议的思考强度？（no_think/think/deep_think）

可用工具：
- rag_search: 从医学知识库检索信息
- diagnosis_match: 判断放射和病理诊断是否相符
- sql_query: 查询数据库统计信息

请按以下JSON格式输出：
{{
    "need_rag": true/false,
    "complexity": "simple|moderate|complex",
    "reasoning": "判断理由",
    "suggested_tools": ["tool1", "tool2"],
    "can_answer_directly": true/false,
    "suggested_thinking_mode": "no_think|think|deep_think"
}}"""

    # ==================== 任务规划 Prompt ====================
    TASK_PLANNING: str = """你是一个任务规划专家。{thinking_instruction}

用户问题：{question}
复杂度：{complexity}

可用工具及其描述：
{tool_descriptions}

请制定执行计划：
1. 将任务分解为最小可执行步骤
2. 识别步骤间的依赖关系
3. 标注哪些步骤可以并行执行
4. 为每个步骤指定最合适的工具

请按以下JSON格式输出：
{{
    "steps": [
        {{
            "id": 1,
            "description": "步骤描述",
            "tool": "tool_name",
            "params": {{"param1": "value1"}},
            "depends_on": [0],
            "can_parallel": false
        }}
    ],
    "estimated_steps": 3,
    "fallback_strategy": "如果失败的备选方案"
}}"""

    # ==================== 答案合成 Prompt ====================
    ANSWER_SYNTHESIS: str = """你叫小语，是放射科医生的专业知识助手。{thinking_instruction}

## 用户问题
{question}

## 检索到的信息
{context}

## 要求
1. 基于检索到的信息回答用户问题
2. 使用专业但易懂的中文
3. 引用来源时标注[数字]格式
4. 不确定的内容明确说明
5. 保持简洁，重点突出

请输出回答内容。"""

    # ==================== 放射-病理诊断匹配 Prompt ====================
    DIAGNOSIS_MATCH: str = """你是放射诊断质控专家，负责判断放射诊断与病理诊断是否相符。{thinking_instruction}

【放射诊断】
{radiology_result}

【病理诊断】
{pathology_result}

【解剖位置匹配分析】
{alignment_info}

请判断两者的符合程度：
1. 分析放射诊断的关键发现
2. 分析病理诊断的关键发现
3. 对比两者的解剖位置和病理性质
4. 给出符合率判断及理由

请按以下JSON格式输出：
{{
    "result": "符合|基本符合|不符合|无法判断",
    "confidence": "高|中|低",
    "reason": "详细的判断理由",
    "key_findings": ["关键发现1", "关键发现2"],
    "suggestions": "建议或注意事项"
}}"""

    # ==================== SQL生成 Prompt ====================
    SQL_GENERATION: str = """你是一个SQL专家。{thinking_instruction}

数据库表结构：
{schema}

相似示例：
{examples}

用户问题：{question}

要求：
1. 只返回SELECT查询语句
2. 使用标准SQL语法
3. 添加必要的WHERE条件过滤
4. 如有聚合需求，使用GROUP BY
5. 使用LIMIT限制返回行数（默认100）

请按以下格式输出：
```sql
SELECT ...
```

如果无法生成SQL，请说明原因。"""

    # ==================== 反思与修正 Prompt ====================
    REFLECTION: str = """你是一个任务反思专家。{thinking_instruction}

原始任务：{task}
执行计划：{plan}
执行结果：{results}
最终输出：{output}

请评估：
1. 结果是否完整回答了原始问题？
2. 执行过程中是否存在错误？
3. 是否有遗漏的步骤？
4. 是否可以优化？

请按以下JSON格式输出：
{{
    "is_satisfactory": true/false,
    "issues": ["问题1", "问题2"],
    "suggested_action": "complete|retry|replan|escalate",
    "reason": "决策理由",
    "new_plan": null
}}"""

    # ==================== 患者分析 Prompt ====================
    PATIENT_ANALYSIS: str = """你是经验丰富的主任医师，擅长总结患者病史并给出阅片要点。{thinking_instruction}

## 患者历史检查记录
{history}

## 即将进行的检查
检查类型：{modality}
检查部位：{studypart}

## 近期相同部位检查
{recent_reports}

请提供：
1. 患者主要疾病按系统总结
2. 阅片时需要特别关注的要点
3. 扫描技术细节建议
4. 鉴别诊断考虑

请以结构化Markdown格式输出。"""

    # ==================== 方法 ====================

    @classmethod
    def get_thinking_instruction(cls, mode: ThinkingMode) -> str:
        """获取思考模式的指令文本

        Args:
            mode: 思考模式

        Returns:
            对应的思考指令
        """
        instructions = {
            ThinkingMode.NO_THINK: cls.NO_THINK_INSTRUCTION,
            ThinkingMode.THINK: cls.THINK_INSTRUCTION,
            ThinkingMode.DEEP_THINK: cls.DEEP_THINK_INSTRUCTION,
        }
        return instructions.get(mode, cls.THINK_INSTRUCTION)

    @classmethod
    def get_prompt(
        cls,
        name: str,
        thinking_mode: Optional[ThinkingMode] = None,
        **kwargs
    ) -> str:
        """获取并格式化Prompt

        Args:
            name: Prompt名称
            thinking_mode: 思考模式，默认使用标准推理
            **kwargs: 其他格式化参数

        Returns:
            格式化后的Prompt
        """
        prompt_template = getattr(cls, name, "")
        if not prompt_template:
            raise ValueError(f"Unknown prompt: {name}")

        # 处理思考模式
        if thinking_mode is None:
            thinking_mode = ThinkingMode.THINK

        thinking_instruction = cls.get_thinking_instruction(thinking_mode)

        # 添加思考指令到参数
        kwargs["thinking_instruction"] = thinking_instruction

        return prompt_template.format(**kwargs)

    @classmethod
    def auto_select_thinking_mode(
        cls,
        complexity: str,
        task_type: str = "general"
    ) -> ThinkingMode:
        """根据任务复杂度自动选择思考模式

        Args:
            complexity: 复杂度级别 (simple/moderate/complex)
            task_type: 任务类型

        Returns:
            推荐的思考模式
        """
        from config.settings import settings

        # 根据复杂度选择
        if complexity == "simple":
            return settings.simple_task_thinking
        elif complexity == "moderate":
            return settings.moderate_task_thinking
        elif complexity == "complex":
            return settings.complex_task_thinking

        # 根据任务类型微调
        if task_type in ["diagnosis_match", "complex_analysis"]:
            return ThinkingMode.DEEP_THINK
        elif task_type in ["direct_answer", "greeting"]:
            return ThinkingMode.NO_THINK

        return ThinkingMode.THINK
