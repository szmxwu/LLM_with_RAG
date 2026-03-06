import json
import os
# Make sure to install the openai library: pip install openai
from openai import OpenAI, APITimeoutError, APIConnectionError, APIStatusError, RateLimitError
from dotenv import load_dotenv
from RAGFLOW_SDK import Create_session
from functools import lru_cache
import re
from json_repair import repair_json
import httpx
import urllib3

# SSL验证配置：通过环境变量控制，默认启用验证
SSL_VERIFY = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
if not SSL_VERIFY:
    # 禁用 InsecureRequestWarning（仅在内部网络明确需要时禁用SSL验证）
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http_client = httpx.Client(verify=SSL_VERIFY)
load_dotenv()

# --- Configuration ---
# IMPORTANT: Adjust BASE_URL to the root of your local API, usually ending in /v1
# Example: Remove /chat/completions if present
LLM_API_BASE_URL = os.getenv('XINFERENCE')
# LLM_API_BASE_URL= os.getenv('BASE_URL')
LLM_MODEL_NAME=os.getenv('LLM_NAME')


# The openai library often expects an API key, even if your local server doesn't use it.
# Use a placeholder like "None" or "dummy".
LLM_API_KEY = os.getenv('LLM_KEY')
MAX_TOKENS_PER_CALL = 8192  # For reference
REQUEST_TIMEOUT = 180.0  # Timeout in seconds (float)

# --- Initialize OpenAI Client ---
try:
    client = OpenAI(
        base_url=LLM_API_BASE_URL,
        api_key=LLM_API_KEY,
        http_client=http_client,
        timeout=REQUEST_TIMEOUT,
    )
    print(f"LLM client initialized for base URL: {LLM_API_BASE_URL}")
except Exception as e:
    print(f"Error initializing LLM client: {e}")
    # Handle initialization error appropriately, maybe exit
    exit(1)


# --- RAG Tool Placeholders (Replace with your actual tool implementations) ---
# (Keep the call_scan_method and call_doctor_assistant functions as defined previously)
def call_scan_method(query: str) -> str:
    """Placeholder for calling the 'scan_method' RAG tool."""
    print(f"--- RAG Tool Called: scan_method --- Query: {query} ---")
    session = Create_session("技师长")
    
    answer = ""
    for ans in session.ask(query, stream=True):
        # print(ans.content[len(cont):], end='', flush=True)
        answer = ans.content
    return answer

def call_doctor_assistant(query: str) -> str:
    """Placeholder for calling the 'doctor_assistant' RAG tool."""
    print(f"--- RAG Tool Called: doctor_assistant --- Query: {query} ---")
    session = Create_session("小影")
    answer = ""
    for ans in session.ask(query, stream=True):
        # print(ans.content[len(cont):], end='', flush=True)
        answer = ans.content
    return answer


# Define the tools structure for the OpenAI API (same as before)
tools = [
    {
        "type": "function",
        "function": {
            "name": "call_scan_method",
            "description": "查询规范化的扫描技术参数。当你需要了解特定检查部位或临床场景的标准扫描方案时使用。",
            "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "描述需要查询的扫描方案"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_doctor_assistant",
            "description": "医学助手，回答具体的医学知识问题。当你需要特定疾病的影像学表现、鉴别诊断等信息时使用。",
            "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "具体的医学问题"}}, "required": ["query"]},
        },
    },
]

# --- LLM Interaction Logic (Using OpenAI library) ---


def execute_llm_step_openai(step_name: str, messages: list) -> dict:
    """
    Executes a single step of the LLM interaction using the openai library, handling tool calls.

    Args:
        step_name: Name of the step for logging.
        messages: A list of message objects for this specific step.

    Returns:
        A dictionary with status and result (content or error message).
    """
    print(f"\n--- Starting LLM Step: {step_name} ---")
    try:
        # print(f"--- {step_name} - Sending request to LLM via openai library ---")
        # print(f"--- {step_name} - Messages: {json.dumps(messages, indent=2, ensure_ascii=False)} ---") # Debug
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            top_p=0.8,
            max_tokens=8192
        )
        # print(f"--- {step_name} - Received LLM response ---")
        # print(response) # Debug the response object

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls  # Access tool_calls attribute

        if tool_calls:
            print(
                f"--- {step_name} - LLM requested tool calls: {len(tool_calls)} ---")
            # IMPORTANT: Append the assistant message with tool_calls before processing
            # Use model_dump() for pydantic v2+
            tool_message=response_message.model_dump()
            tool_message['content']=''
            messages.append(tool_message)

            available_functions = {
                "call_scan_method": call_scan_method,
                "call_doctor_assistant": call_doctor_assistant,
            }

            # Execute tool calls and append results
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                tool_call_id = tool_call.id  # Get the tool_call_id

                function_to_call = available_functions.get(function_name)
                if not function_to_call:
                    print(
                        f"Error: Unknown function '{function_name}' in step {step_name}")
                    messages.append({"role": "tool", "tool_call_id": tool_call_id, "name": function_name,
                                    "content": f"Error: Function '{function_name}' not found."})
                    continue

                try:
                    # Arguments are already parsed as a string by the library
                    function_args = json.loads(tool_call.function.arguments)
                    query_arg = function_args.get("query")
                    if query_arg is None:
                        raise ValueError("Missing 'query' argument.")

                    print(
                        f"--- {step_name} - Executing function: {function_name} ---")
                    function_response = function_to_call(query=query_arg)
                    print(
                        f"--- {step_name} - function returned: {len(function_response)} tokens---")
                    # Append the tool response message
                    messages.append({"role": "tool", "tool_call_id": tool_call_id,
                                    "name": function_name, "content": function_response})
                    print(
                        f"--- {step_name} - Added tool response for {function_name} ---")

                except json.JSONDecodeError:
                    print(
                        f"Error: Could not decode arguments for {function_name}: {tool_call.function.arguments}")
                    messages.append({"role": "tool", "tool_call_id": tool_call_id,
                                    "name": function_name, "content": "Error: Invalid arguments format."})
                except Exception as e:
                    print(
                        f"Error executing/parsing tool call {function_name} in step {step_name}: {e}")
                    messages.append({"role": "tool", "tool_call_id": tool_call_id,
                                    "name": function_name, "content": f"Error executing tool: {str(e)}"})

            # Re-call LLM within the same step after processing tools
            print(f"--- {step_name} - Re-calling LLM after tool use ---")
            # *** Pass the UPDATED messages list ***
            # print(messages)
            return execute_llm_step_openai(step_name, messages)

        else:
            # Final response for this step
            final_content = response_message.content
            final_content=re.sub(r'<think>.*?</think>', '', final_content,flags=re.DOTALL)
            if final_content is None:
                print(
                    f"Error: LLM response missing content in step {step_name}")
                print(f"Response Message: {response_message}")
                return {"status": "error", "message": f"LLM response missing content in step {step_name}"}

            print(f"--- Finished LLM Step: {step_name} ---")
            return {"status": "success", "content": final_content}

    # Catch specific OpenAI errors
    except APITimeoutError:
        print(f"Error: OpenAI API request timed out during step {step_name}")
        return {"status": "error", "message": f"Request timed out in step {step_name}"}
    except APIConnectionError as e:
        print(
            f"Error: Failed to connect to OpenAI API during step {step_name}: {e}")
        return {"status": "error", "message": f"API connection error in step {step_name}: {e}"}
    except RateLimitError as e:
        print(
            f"Error: OpenAI API rate limit exceeded during step {step_name}: {e}")
        return {"status": "error", "message": f"API rate limit error in step {step_name}: {e}"}
    except APIStatusError as e:
        print(
            f"Error: OpenAI API returned an error status during step {step_name}: {e}")
        return {"status": "error", "message": f"API status error in step {step_name}: {e.status_code} - {e.response}"}
    except Exception as e:
        print(f"An unexpected error occurred during step {step_name}: {e}")
        # Consider logging the full messages list that caused the error
        # print(f"--- Error occurred with messages: {json.dumps(messages, indent=2, ensure_ascii=False)} ---")
        return {"status": "error", "message": f"An unexpected error in step {step_name}: {e}"}


# --- Main Agent Logic (Sequential Steps - unchanged logic, uses new LLM function) ---
@lru_cache(maxsize=256)
def generate_guidance_sequential_openai(patient_history: str, scan_location: str, scan_device_type: str, previous_scan_results: str) -> str:
    """
    Generates radiographic reading guidance using sequential LLM calls via the openai library.
    """
    history_list=json.loads(repair_json(patient_history))
    reports_list=json.loads(repair_json(previous_scan_results))
    if len(history_list)>0:
        ordered_keys=['date',"modality","result_str"]
        result=[]
        for item in history_list:
            line=','.join(f"{key}:{item[key]}" for key in ordered_keys)
            line=line.replace("modality","类型")
            line=line.replace("result_str","结果")
            line=line.replace("date","日期")
            line=line.replace("US","超声")        
            line=line.replace("PS","病理")
            line=line.replace("ES","内镜")
            result.append("- "+line)
        patient_history="\n".join(result)
        ordered_keys=['date',"part","modality","result"]
        result=[]
        for item in reports_list:
            line=','.join(f"{key}:{item[key]}" for key in ordered_keys)
            line=line.replace("modality","类型")
            line=line.replace("result","结果")
            line=line.replace("date","日期")
            line=line.replace("part","检查部位")
            result.append("- "+line)
        previous_scan_results="\n".join(result)
    
    print("--- Starting patient history summary (using openai library) ---")
    results = {}
    base_system_prompt = """
    你是一个经验丰富、具有深刻洞察力的主任医师，擅长用简洁的语言指出疾病的核心要点。
    请严格按照当前步骤的要求进行回应，只生成当前步骤要求的内容。
    """

    # --- Step 0: patient history summary ---
    step0_user_prompt = f"""
    **当前任务：将患者的疾病按照人体解剖系统进行总结**
    请根据以下信息，生成用于指导年轻医生的 Markdown 格式的“## 病史总结”部分内容。
    如果需要特定的医学知识（如疾病征象），请使用 `call_doctor_assistant` 工具查询。
    **患者信息概要:**
    {patient_history}
    """
    messages_step0 = [
        {"role": "system", "content": base_system_prompt +
            "\n你的输出应仅包含 Markdown 格式的 '## 病史总结' 标题和其下的列表内容。"},
        {"role": "user", "content": step0_user_prompt}
    ]
    # Use the new openai-based function
    result_step0 = execute_llm_step_openai("Parameters", messages_step0)
    if result_step0["status"] != "success":
        return result_step0
    patient_history = result_step0["content"]
    
    
    print("--- Starting Sequential Guidance Generation (using openai library) ---")
    results = {}
    base_system_prompt = """
    你是一位经验丰富的放射科主任医师 RadGuide Pro。你的任务是分步指导一位年轻医生阅片。
    请严格按照当前步骤的要求进行回应，只生成当前步骤要求的内容。
    """

    # --- Step 1: Generate Scan Parameters ---
    step1_user_prompt = f"""
    **当前任务：生成扫描技术参数部分**
    请根据以下信息，生成用于指导年轻医生的 Markdown 格式的“## 扫描技术参数”部分内容。
    重点是提供规范化的扫描参数建议。如果需要标准协议，请使用 `call_scan_method` 工具查询。
    **患者信息概要:**
    - 检查部位: {scan_location}
    - 检查设备类型: {scan_device_type}
    - 简要临床信息（供参考）: {patient_history[:200]}...
    """
    messages_step1 = [
        {"role": "system", "content": base_system_prompt +
            "\n你的输出应仅包含 Markdown 格式的 '## 扫描技术参数' 标题和其下的列表内容。"},
        {"role": "user", "content": step1_user_prompt}
    ]
    # Use the new openai-based function
    result_step1 = execute_llm_step_openai("Parameters", messages_step1)
    if result_step1["status"] != "success":
        return result_step1
    results["parameters"] = result_step1["content"]
    # time.sleep(0.5) # Optional delay

    # --- Step 2: Generate Reading Details ---
    step2_user_prompt = f"""
    **当前任务：生成阅片关注细节部分**
    基于以下完整信息，并参考已生成的扫描参数，请生成用于指导年轻医生的 Markdown 格式的“## 阅片关注细节”部分内容。
    重点是列出阅片时应重点观察的解剖结构、潜在异常、关键指标。内容需具体、有针对性。如果需要特定的医学知识（如疾病征象），请使用 `call_doctor_assistant` 工具查询。
    **患者详细病史:**
    {patient_history}
    **当前检查部位:** {scan_location}
    **检查设备类型:** {scan_device_type}
    **既往同部位检查结果:** {previous_scan_results if previous_scan_results else "无"}
    """
    messages_step2 = [
        {"role": "system", "content": base_system_prompt +
            "\n你的输出应仅包含 Markdown 格式的 '## 阅片关注细节' 标题和其下的列表/段落内容。"},
        {"role": "user", "content": step2_user_prompt}
    ]
    result_step2 = execute_llm_step_openai("Details", messages_step2)
    if result_step2["status"] != "success":
        return result_step2
    results["details"] = result_step2["content"]
    # time.sleep(0.5) # Optional delay

    # --- Step 3: Generate Comprehensive Considerations ---
    step3_user_prompt = f"""
    **当前任务：生成综合考虑因素部分**
    基于以下所有信息，包括病史、检查信息以及先前生成的“扫描参数”和“阅片细节”，请生成用于指导年轻医生的 Markdown 格式的“## 综合考虑因素”部分内容。
    重点是结合所有信息提出鉴别诊断思路、潜在陷阱、对比旧片、以及临床建议。如果需要特定医学知识，请使用 `call_doctor_assistant` 工具查询。
    **患者详细病史:**
    {patient_history}
    **当前检查部位:** {scan_location}
    **检查设备类型:** {scan_device_type}
    **既往同部位检查结果:** {previous_scan_results if previous_scan_results else "无"}
    **已生成的阅片关注细节:**
    {results["details"]}
    """
    messages_step3 = [
        {"role": "system", "content": base_system_prompt +
            "\n你的输出应仅包含 Markdown 格式的 '## 综合考虑因素' 标题和其下的列表/段落内容。"},
        {"role": "user", "content": step3_user_prompt}
    ]
    result_step3 = execute_llm_step_openai("Considerations", messages_step3)
    if result_step3["status"] != "success":
        return result_step3
    results["considerations"] = result_step3["content"]

    # --- Step 4: Combine Results ---
    final_markdown = f"""# 阅片指导：{scan_location} {scan_device_type}
    **患者信息概要:** 
    
    - **检查部位:** {scan_location}
    
    - **检查设备:** {scan_device_type}
    
    {patient_history}

    ---
    
    {results.get("parameters", "## 扫描技术参数：*未能生成*")}
    
    ---
    
    {results.get("details", "## 阅片关注细节：*未能生成*")}
    
    ---
    
    {results.get("considerations", "## 综合考虑因素：*未能生成*")}
    
    ---
    
    **免责声明:** 本指导意见仅供学习参考，不能替代最终诊断决策。
    """

    print("--- Finished Sequential Guidance Generation (using openai library) ---")
    return final_markdown


# --- Example Usage ---
if __name__ == "__main__":
    # Example 1: Acute Stroke Scenario (Potentially long history)
    print("\n--- Example 1: Acute Stroke (Sequential + OpenAI Lib) ---")
    history1 = """
                      [{"modality": "申请单", "result_str": "病史:。主诉：协诊体格检查：诊断:头晕查因","date":"2025-3-18 16:17:13"},
                        {"modality": "CT", "result_str": "急诊报告1.原两肺炎症，现片明显吸收好转。现左下肺仍可见少量炎症，建议抗炎治疗后随诊复查。2.左肺上叶术后改变，左肺门饱满，大致同前，建议随诊复查。双肺多发小结节，同前相仿，随访复查。右侧斜裂陈旧灶；肺气肿；双肺少许支扩。3.左膈膨隆。心包少许积液。双侧胸腔少量积液现基本吸收。4.主动脉硬化。5.附见肝脏钙化灶。","date":"2024-10-13 15:56:27"},
                        {"modality": "CT", "result_str": "1.双肺炎症，较前进展。2.左肺上叶术后改变，左肺门饱满，大致同前，建议随诊复查。双肺多发小结节，同前相仿，随访复查。右侧斜裂陈旧灶；肺气肿；双肺少许支扩。3.左膈膨隆。心包少许积液，较前吸收。双侧胸腔少量积液。4.主动脉硬化。","date":"2024-3-25 16:01:54"},
                        {"modality": "CT", "result_str": "急诊报告：1.颈椎反弓，颈椎退行性变。颈45、56椎间病损，必要时进一步检查。2.腰椎退行性变。腰34-腰5骶1椎间盘膨出，请结合临床必要时进一步检查。","date":"2023-10-11 10:54:34"},
                        {"modality": "MR", "result_str": "1.双侧额顶叶、基底节区缺血灶较前稍增多；脑小血管病变，Fazekas 1级；老年脑。2.脑动脉硬化。3.附见：副鼻窦少许炎症。请结合临床。","date":"2023-8-21 21:07:05"},
                        {"modality": "CT", "result_str": "1.双侧胸腔积液，较前减少；双下肺炎症，以左肺下叶明显，较前明显吸收。2.左肺上叶术后改变，左肺门饱满，大致同前，建议随诊复查。双肺多发小结节，随访复查。右侧斜裂陈旧灶；肺气肿；双肺少许支扩。3.左膈膨隆。心包少许积液。4.主动脉硬化。","date":"2023-7-19 11:08:54"},
                        {"modality": "DR", "result_str": "左肺术后改变；左侧胸腔少量积液待排，原左侧部分肺组织膨胀不全较前略改善；左肺炎症较前吸收减少；左膈面升高；右肺少许炎症可能；请结合临床及相关检查考虑、随访。","date":"2023-3-20 16:12:15"},
                        {"modality": "DR", "result_str": "左肺术后改变；左侧胸腔积液可能，左侧部分肺组织膨胀不全可能；左肺炎症；请结合临床及相关检查考虑、随访。","date":"2023-3-17 10:52:18"},
                        {"modality": "DR", "result_str": "左肺术后改变；左下肺慢性炎症；请结合临床。","date":"2023-3-15 19:59:44"},
                        {"modality": "CT", "result_str": "急诊报告：双侧额顶叶、基底节区、桥脑腔隙性脑梗塞及缺血灶。所见均前相仿。必要时MRI。","date":"2023-3-14 15:37:15"},
                        {"modality": "CT", "result_str": "急诊报告：1.双侧额顶叶、基底节区、桥脑腔隙性脑梗塞及缺血灶。必要时MRI。2.新见左侧胸腔积液，双肺炎症，以左肺下叶明显。3.左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚。原双肺多个小结节，部分现显示不清。右侧斜裂陈旧灶；肺气肿。右肺散在慢性炎症。左膈膨隆。心包少许积液。左肺门可疑软组织影，肿大淋巴结可能。4.间位结肠；肝右前叶包膜下钙化灶；同前相仿。升结肠憩室。脐部腹壁密度增高。附见左肾上腺粗。","date":"2023-3-13 17:57:09"},
                        {"modality": "CT", "result_str": "1.左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚；2.原右肺上叶后段斑块状影现未见。 3.双肺多个小结节同前相仿，拟良性。右侧斜裂陈旧灶；肺气肿。双下肺少许慢性炎症。4.左膈膨隆。5.附见：间位结肠；肝右前叶包膜下钙化灶；同前相仿。","date":"2023-3-10 8:45:15"},
                        {"modality": "CT", "result_str": "急诊报告：1、左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚；2、右肺上叶后段新见斑块状影，考虑炎症可能，建议治疗后复查除外其他。 3、双肺多个小结节；同前相仿。右侧斜裂陈旧灶；肺气肿。双下肺少许慢性炎症。4、左膈膨隆。5、双侧额顶叶、基底节区少许缺血灶、腔梗，老年脑；请结合临床必要时MRI检查。6、附见：间位结肠；肝右前叶包膜下钙化灶；同前相仿。右侧上颌窦及左侧蝶窦炎症。","date":"2022-11-10 13:32:48"},
                        {"modality": "CT", "result_str": "1、双肺少许支气管扩张伴周围炎症，大致同前。 2、左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚；双肺多个小结节；同前相仿。3、右侧斜裂陈旧灶；肺气肿；心包少量积液较前减少。4、附见：间位结肠；肝右前叶包膜下钙化灶；同前相仿。请结合临床。","date":"2022-9-30 14:03:37"},
                        {"modality": "DR", "result_str": "左肺术后改变，左下肺少许炎症现已吸收；左上胸膜增厚。请结合临床。","date":"2022-8-4 14:16:46"},
                        {"modality": "CT", "result_str": "急诊报告：1、双肺少许支气管扩张伴周围炎症，大致同前。 2、“左上肺腺癌术后”复查，术区周围少许慢性炎症并邻近胸膜增厚，同前相仿；双肺数枚小结节，大致同前。3、右侧斜裂陈旧灶；肺气肿；心包少量积液，大致同前。4、附见：间位结肠；肝右前叶包膜下钙化灶。","date":"2022-2-6 9:34:31"},
                        {"modality": "MR", "result_str": "1.双侧额顶叶白质多发缺血灶，老年脑改变，基本相仿。2.颅脑MRA：脑动脉硬化。3.附见：蝶窦炎。","date":"2021-12-30 8:37:04"},
                        {"modality": "CT", "result_str": "急诊报告：1、双肺少许支气管扩张伴周围炎症，较前有所吸收。 2、“左上肺腺癌术后”复查，术区周围少许慢性炎症并邻近胸膜增厚，同前相仿；双肺数枚小结节，大致同前。3、右侧斜裂陈旧灶；肺气肿；心包少量积液，较前吸收。4、附见：间位结肠；肝右前叶包膜下钙化灶。","date":"2021-8-19 9:19:19"},
                        {"modality": "CT", "result_str": "急诊报告：1、双肺少许支气管扩张伴周围炎症。 2、“左上肺腺癌术后”复查，术区周围少许慢性炎症并邻近胸膜增厚，同前相仿；双肺数枚小结节，大致同前。3、右侧斜裂陈旧灶；心包少量积液，较前稍增多。4、附见：间位结肠；肝右前叶包膜下钙化灶。","date":"2021-4-22 10:45:58"},
                        {"modality": "CT", "result_str": "1、 “左上肺腺癌术后”复查，术区周围少许慢性炎症并邻近胸膜增厚，同前相仿；右下肺新见少许炎症；余双肺数枚小结节，部分现未见显示，余同前。2、右侧斜裂陈旧灶；心包少量积液。同前。3、附见：间位结肠；肝右前叶包膜下钙化灶。","date":"2021-1-26 8:52:55"},
                        {"modality": "CT", "result_str": "1、 “左上肺腺癌术后”复查，术区周围少许慢性炎症并邻近胸膜增厚；余双肺多发小结节同前，建议随访复查；右侧斜裂陈旧灶；心包少量积液。2、附见：间位结肠；肝右前叶包膜下钙化灶。","date":"2020-7-30 12:58:35"},
                        {"modality": "CT", "result_str": "1.冠状动脉未见钙化。2.冠状动脉造影未见明确狭窄或斑块。3.心包前壁局限生增厚；主动脉硬化，主动脉弓降部瘤样扩张。请结合临床。","date":"2020-5-20 14:27:32"},
                        {"modality": "DR", "result_str": "左肺术后改变：左下肺少许炎症，较前相仿；左侧少量胸腔积液；左上胸膜增厚。","date":"2020-4-10 15:49:55"},
                        {"modality": "DR", "result_str": "左肺术后改变：左肺渗出灶较前吸收，左侧少许气胸较前吸收，左侧胸壁皮下气肿较前好转。左上胸膜增厚。","date":"2020-3-29 11:11:34"},
                        {"modality": "DR", "result_str": "1.左肺术后改变：左下肺渗出灶，左侧少许气胸可能，左侧胸壁皮下气肿。2.右侧叶间积液？3.必要时进一步检查或追踪复查，详请贵科阅片并密切结合临床考虑。","date":"2020-3-25 21:40:50"},
                        {"modality": "MR", "result_str": "双侧额顶叶白质少许小缺血灶。","date":"2020-3-14 14:30:48"},
                        {"modality": "CT", "result_str": "1、左肺上叶尖后段磨玻璃阴影，其内肺纹理通过并增粗，拟肿瘤性病变可能。建议相关性检查。余两肺多发小结节，建议随诊复查。2、附见：间位结肠；肝右叶包膜下钙化灶。","date":"2020-3-10 8:57:40"},
                        {"modality":"住院","result_str":" 1.帕金森病 2.腔隙性脑梗死 3.高血压病3级（极高危） 4.颈动脉硬化 5.睡眠障碍 6.胸腔积液 7.肺肿物 8.无症状性菌尿 9.左肺上叶恶性肿瘤","date":"2023-8-19 00:00:00"},
                        {"modality":"住院","result_str":" 1.安眠药中毒 2.腔隙性脑梗死 3.肺炎 4.低钾血症 5.胸腔积液 6.镇静剂、催眠药和抗焦虑药的有害效应，其他的 7.左肺上叶恶性肿瘤 8.肺肿瘤 9.肺肿物 10.肺气肿 11.低蛋白血症 12.高血压病3级（极高危） 13.帕金森病 14.睡眠障碍 15.白内障 16.肝肿物 17.脂肪肝 18.间位结肠 19.前列腺增生 20.下肢动脉粥样硬化","date":"2023-3-14 00:00:00"},
                        {"modality":"住院","result_str":" 1.老年性白内障 2.高血压 3.帕金森病","date":"2022-8-4 00:00:00"},{"modality":"住院","result_str":" 1.肺上叶恶性肿瘤 2.腺癌 3.肺肿物 4.高血压3级 5.帕金森病","date":"2020-3-12 00:00:00"},
                        {"modality": "US", "result_str": "静息状态下左室未见明显室壁运动异常左室射血分数正常左室舒张功能正常右室收缩功能正常","date":"2025-3-17 16:24:00"},
                        {"modality": "US", "result_str": "双侧颈动脉分叉粥样硬化斑块形成，斑块处管腔未见明显狭窄。双侧颈总动脉内中膜增厚。双侧椎动脉未见明显异常。","date":"2023-8-23 8:59:57"},
                        {"modality": "US", "result_str": "左房扩大二尖瓣少量反流三尖瓣少量反流静息状态下左室未见明显室壁运动异常左室射血分数正常左室舒张功能减低右室收缩功能正常","date":"2023-8-21 14:27:16"},
                        {"modality": "US", "result_str": "双侧下肢动脉粥样硬化斑块形成，未见明显狭窄。双侧下肢深静脉未见明显异常声像。","date":"2023-3-14 16:45:27"},
                        {"modality": "US", "result_str": "主动脉硬化；静息状态下未见明显室壁运动异常；左室整体收缩功能正常。建议在患者条件许可时，来我科进一步详细检查。","date":"2023-3-14 16:43:08"},
                        {"modality": "US", "result_str": "肝回声不均，考虑轻度脂肪肝。胆囊、胆管、脾脏、胰腺及门静脉系统：未见明显异常声像。右肾内结石。左肾未见明显异常。输尿管:未见明显扩张。膀胱未充盈。前列腺增生并结石。","date":"2023-3-14 16:39:00"},
                        {"modality": "US", "result_str": "主动脉硬化；静息状态下未见明显室壁运动异常；心功能正常。","date":"2022-11-10 14:36:01"},
                        {"modality": "US", "result_str": "二尖瓣、三尖瓣少量反流静息状态下未见明显室壁运动异常左室射血分数正常左室舒张功能减低","date":"2021-8-19 11:08:03"},
                        {"modality": "PS", "result_str": "冰冻后石蜡（左上肺结节）浸润性肺腺癌，中分化，腺泡70%+贴壁30%，肿物最大径分别为1cm及0.8cm，局部可见癌细胞沿气腔传播，脉管内见癌细胞，未见神经累犯，胸膜及吻合钉切缘未见癌；癌旁肺组织伴较多碳尘聚集及纤维组织增生。IHC：CK7（+）、CK56（-）、TTF-1（+）。","date":"2020-3-31 15:57:42"},
                        {"modality": "PS", "result_str": "（第5.6组、第10组）淋巴结未见癌（02、01）。","date":"2020-3-30 18:33:45"},
                        {"modality": "PS", "result_str": "（左上肺结节）肺腺癌，以贴壁生长为主型，吻合钉切缘未见癌。","date":"2020-3-25 10:43:20"},
                        {"modality": "US", "result_str": "肝回声不均，考虑轻度脂肪肝。胆囊、胆管、脾脏、胰腺及门静脉系统：未见明显异常声像。右肾内结石。左肾未见明显异常。双侧肾上腺:未见明显异常声像。","date":"2020-3-20 9:38:53"},
                        {"modality": "PS", "result_str": "“支气管刷检”：见纤毛柱状上皮细胞，杯状细胞，未见明确肿瘤细胞。","date":"2020-3-19 16:38:15"},
                        {"modality": "ES", "result_str": "气管、支气管腔内未见异常经支气管肺泡灌洗术经支气管刷检术","date":"2020-3-17 17:57:04"},
                        {"modality": "US", "result_str": "双侧颈部及锁骨上未见明显异常。","date":"2020-3-13 9:29:57"},
                        {"modality": "US", "result_str": "心脏形态结构及瓣膜活动未见明显异常；静息状态下未见明显室壁运动异常；心功能正常。","date":"2020-3-13 8:36:13"}]
                      """
    location1 = "头颅"
    device1 = "CT"
    previous1 = "患者诉1年前曾因头晕于外院行头颅CT，结果回报大致正常，具体报告未带来。"

    # Call the function using the openai library implementation
    guidance1 = generate_guidance_sequential_openai(
        history1, location1, device1, previous1)


    print(guidance1)


