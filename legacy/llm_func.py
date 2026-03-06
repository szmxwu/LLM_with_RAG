from RAGFLOW_SDK import (Download_document, 
                         List_documents, 
                         Upload_documents, 
                         List_datasets, 
                         Create_dataset, 
                         Delete_documents, 
                         Parse_documents, 
                         Stop_parsing, 
                         Retrieve_chunks, 
                         BASE_URL, 
                         Agent_chat, 
                         Show_all_datasets, 
                         Show_all_docs,
                         List_chunks
                         )
from process_docs import pdf_page_to_image,RAGFlowPptParser
import re
import os
import time
import json
import subprocess
import requests
import pandas as pd
import numpy as np
import warnings
from pprint import pprint
from bs4 import BeautifulSoup
import sqlalchemy as sql
from keyword_extraction import get_orientation_position
import configparser
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import load_prompt, PromptTemplate
from langchain_openai import ChatOpenAI
import base64
import asyncio
from radiology_Agent import execute_llm_step_openai
from json_repair import repair_json
from langchain_community.embeddings import XinferenceEmbeddings
from functools import lru_cache
from dotenv import load_dotenv
import logging
import httpx
import urllib3

# SSL验证配置：通过环境变量控制，默认启用验证
SSL_VERIFY = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
if not SSL_VERIFY:
    # 禁用 InsecureRequestWarning（仅在内部网络明确需要时禁用SSL验证）
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
http_client = httpx.Client(verify=SSL_VERIFY)
logger=logging.getLogger(__name__)
warnings.filterwarnings('ignore')
load_dotenv()
# 访问环境变量
# 项目根目录路径（用于资源文件定位）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 资源文件目录
_CONFIG_DIR = os.path.join(_PROJECT_ROOT, 'resources', 'config')
_DICTIONARIES_DIR = os.path.join(_PROJECT_ROOT, 'resources', 'dictionaries')
PATH_MATCH_REPLACE_FILE = os.path.join(_DICTIONARIES_DIR, 'match_replace.xlsx')
LLM_NAME = os.getenv('LLM_NAME')
XINFERENCE = os.getenv('XINFERENCE')
ODBC = os.getenv('ODBC')
RERANK_ID = os.getenv('RERANK_ID')
EMBEDDING = os.getenv('EMBEDDING')
LLM_KEY= os.getenv('LLM_KEY')
CACHE_DIR = os.path.join(_PROJECT_ROOT, 'cache')
conf = configparser.ConfigParser()
conf.read(os.path.join(_CONFIG_DIR, 'system_config.ini'), encoding="utf-8")

# 文本词汇清洗
match_replace = pd.read_excel(
    PATH_MATCH_REPLACE_FILE, sheet_name=0).to_dict('records')
# 连接数据库
connectionString = ODBC
engine = sql.create_engine(connectionString)
# 连接大模型
llm = ChatOpenAI(
    base_url=XINFERENCE,
    model=LLM_NAME,
    api_key=LLM_KEY,
    http_client=http_client
)


# 获取当前文件所在目录的父目录（项目根目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_DIR = os.path.join(_PROJECT_ROOT, 'prompt')

# 读取预设提示词
sql_prompt_file = load_prompt(os.path.join(_PROMPT_DIR, 'sql_prompt.json'))
match_prompt_file = load_prompt(
    os.path.join(_PROMPT_DIR, 'match_prompt_template.json'))
complex_match_prompt = load_prompt(
    os.path.join(_PROMPT_DIR, 'complex_match_prompt.json'))
# fig_prompt_file = load_prompt(os.path.join(_PROMPT_DIR, 'fig_prompt_template.json'))
judge_prompt_file = load_prompt(
    os.path.join(_PROMPT_DIR, 'judge_prompt_template.json'))
with open(os.path.join(_PROMPT_DIR, 'fig_prompt.txt'), 'r', encoding='utf-8') as file:
    fig_prompt = file.read()



def generate_probe(answer):
    """
    生成追问关键词，用于查询病例库
    """
    probe_path = os.path.join(_PROMPT_DIR, 'probe_prompt.txt')
    with open(probe_path, 'r', encoding='utf-8') as file:
        probe_prompt = file.read()
    probe_prompt = probe_prompt.replace("{answer}", answer)
    parser = StrOutputParser()
    messages = [
        SystemMessage(content="你是一个经验丰富的医学专业英语编辑，帮助用户处理医学文本/no_think"),
        HumanMessage(content=probe_prompt),
        ]
    
    result = parser.invoke(llm.invoke(messages))
    # print(result)
    result=re.sub(r'<think>.*?</think>', '', result,flags=re.DOTALL)
    scucess=False
    for i in range(3):
        try:
            sentence=result.replace("_", " ").split("\n")
            sentence=[x for x in sentence if x]
            long_keywords=[x for x in sentence[1].split(" ") if x!='']
            short_keywords=[x for x in sentence[2].split(" ") if x!='']
            if len(long_keywords)>5:
                keywords=short_keywords
            else:
                keywords=long_keywords
            if not "".join(keywords).isalnum():
                raise ValueError("输出格式错误")
            scucess=True
            break
        except:
            print(f"关键词格式提取有误'{keywords}'，第{i}遍重新提取")
            messages.append(
                AIMessage(keywords)
            )
            messages.append(
                HumanMessage("你没有按照格式要求输出, 请重新输出。")
            )
            keywords = parser.invoke(llm.invoke(messages))

    # 将关键词返回显示在界面的回答下方，用户可点击关键词进行搜索
    # print("相关病例关键词:",keywords)
    if scucess:
        return " ".join(keywords)
    else:
        return ''


def search_case(keywords):
    """
    根据关键词搜索病例库
    弹出新的页面，用列表+图像展示病例
    """
    cases = Retrieve_chunks(keywords, '病例', "", 20)
    result = []
    for case in cases:
        filname=case.document_name
        filname=filname.replace(".md","")
        html_content=f"<h3>{filname}</h3><br>{case.content}"
        ##把图片转化为base64编码后发送，注意图片文件的路径格式为pictures\000002.png
        pattern = re.compile(r'<img[^>]+src=["\']([^">]+)["\'].*?>', re.IGNORECASE)
        matches = pattern.findall(html_content)
        for img_path in matches:
            if os.path.exists(img_path.replace("\\","/")):
                with open(img_path.replace("\\","/"),"rb") as image_file:
                    images_base64=base64.b64encode(image_file.read()).decode("utf-8")
                    html_content=html_content.replace(img_path,f"data:image/png;base64,{images_base64}")
            else:
                print(f"{img_path}未找到")
        result.append(html_content)
    return result



def get_pdf_content(chunk):
    doc_id=chunk['document_id']
    doc_name=chunk['document_name']
    page=chunk['page']
    exists, filepath = check_cache(doc_name)
    if not exists:
        print("Downloading file...")
        filepath = Download_document(doc_id, doc_name)
    else:
        print(f"{doc_name} is in cache")
    content=f"<h3>{doc_name}</h3><br>"
    for p in page:
        # 把页面转化为图片
        img_path = pdf_page_to_image(filepath, p)
        # 返回图片
        if os.path.exists(img_path):
            with open(img_path,"rb") as image_file:
                image_base64=base64.b64encode(image_file.read()).decode("utf-8")
                content += f'<img src="data:image/png;base64,{image_base64}" alt="图片" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
        else:
            print("文件不存在：",img_path)
    # print(content)
    return content



def get_ppt_content(chunk):
    doc_id=chunk['document_id']
    doc_name=chunk['document_name']
    page=chunk['page']
    content=chunk['content']
    exists, filepath = check_cache(doc_name)
    if not exists:
        print("Downloading file...")
        filepath = Download_document(doc_id, doc_name)
    else:
        print(f"{doc_name} is in cache")
    
    #缺少页码的处理方式
    if not page:
        pptParser=RAGFlowPptParser()       
        page=pptParser( filepath, content)
        if not page:
            return None
        else:
            page=[page]
    # 转化为pdf
    pdfpath = os.path.splitext(filepath)[0]+".pdf"
    if os.path.exists(pdfpath):
        filepath = pdfpath
        print(f"{pdfpath} is exists in cache")
    else:
        cmd = ["soffice", "--headless", "--convert-to", "pdf:writer_pdf_Export",
               "cache\\"+doc_name, "--outdir", "cache"]
        try:
            # subprocess.run(cmd,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            subprocess.run(cmd, capture_output=True)
        except Exception as e:
            print(e)
        if os.path.exists(pdfpath):
            print("pdf convert succeeded.")
            filepath = pdfpath
        else:
            print("pdf convert failed ")
            return ""
    content=f"<h3>{doc_name}</h3><br>"
    for p in page:
        # 把页面转化为图片
        img_path = pdf_page_to_image(filepath, p)
        # 返回图片
        if os.path.exists(img_path):
            with open(img_path,"rb") as image_file:
                image_base64=base64.b64encode(image_file.read()).decode("utf-8")
                content += f'<img src="data:image/png;base64,{image_base64}" alt="图片" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
    return content

def get_img_base64(img_id:str):
    img_url=f"{BASE_URL}/v1/document/image/{img_id}"
    response=requests.get(img_url)
    if response.status_code==200:
        return base64.b64encode(response.content).decode("utf-8")
    else:
        return None

def get_other_content(chunk):
    """处理其他类型引文的显示"""
    @lru_cache(maxsize=1000)
    def cached_content(
        filename:str,
        content_ltks:str,
        img_id:str,
        doc_id:str,
        dataset_id:str,
    )->str:

        # content_ltks = content_ltks.replace("。", "。<br>")
        content = f"<h3>{filename}</h3><br>{content_ltks}<br>"
        # 显示图片，特别重要
        if img_id:
            image_base64=get_img_base64(img_id)
            content += f'<img src="data:image/png;base64,{image_base64}" alt="图片" id="{img_id}" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
        all_chunks=List_chunks(dataset_id,doc_id)
        #查找前后的图片
        start=time.time()
        try:
            target_index=next(i for i,d in enumerate(all_chunks) if d.id==chunk['id'])
        except StopIteration:
            target_index=None
        prev=all_chunks[target_index-1] if target_index>0 else None
        next_item=all_chunks[target_index+1] if target_index<len(all_chunks)-1 else None
        # print(f"查找前后的图片耗时：{time.time()-start}")
        if prev is not None:
            if prev.image_id:
                image_base64=get_img_base64(prev.image_id)
                content += f'<img src="data:image/png;base64,{image_base64}" alt="图片" id="{prev.image_id}" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
        if next_item is not None:
            if next_item.image_id:
                content+=next_item.content+"<br>"
                image_base64=get_img_base64(next_item.image_id)
                content += f'<img src="data:image/png;base64,{image_base64}" alt="图片" id="{next_item.image_id}" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
        return content
    return cached_content(
        filename=chunk['document_name'],
        content_ltks=chunk['content'],
        img_id=chunk['image_id'],
        doc_id=chunk['document_id'],
        dataset_id=chunk['dataset_id'],
    )

def check_cache(filename):
    """Check if the file exists in the cache directory."""
    filepath = os.path.join(CACHE_DIR, filename)
    return os.path.exists(filepath), filepath


def get_LLM_SQL(question: str):
    """
    首先调用ragflow查找最相似的examples来优化prompt，
    然后使用llm把question转化为SQL
    最后分析是否可以可视化
    """
    df = []
    # 获得最接近的SQL示例
    examples = Retrieve_chunks(question, 'SQL', "rmyy_DB.xlsx", 3)
    examples = [d.content.replace("\\n", "").replace(
        "\n", "").replace("\'", "'") for d in examples]
    print("example:", [re.findall("问题：(.*?)回答", d) for d in examples])
    examples = "\n\n".join(examples)
    prompt_str = sql_prompt_file.format(content=question, examples=examples)
    # print(prompt_str)
    messages = [
        SystemMessage(content="你是一个SQL工程师，帮助用户编写SQL语言"),
        HumanMessage(content=prompt_str),
    ]
    # 输出解析
    parser = StrOutputParser()
    parseStr = parser.invoke(llm.invoke(messages))
    if "select" not in parseStr.lower():
        return [], parseStr, df
    mat = re.search(r'```sql(.*?)```', parseStr,
                    re.DOTALL | re.MULTILINE | re.I)
    if mat:
        sql_str = mat.group(1)
    else:
        sql_str = parseStr
    # sql_str=parseStr.replace("```","").replace("sql","")
    for n in range(5):
        try:
            sql_str = re.sub("B超|超声|彩超", "US", sql_str)
            sql_str = re.sub("病理|免疫组化", "PS", sql_str)
            sql_str = re.sub("内镜|胃肠镜|胃镜|肠镜|阴道镜|宫腔镜", "ES", sql_str)
            sql_str = re.sub("磁共振|MRI|核磁|核磁共振", "MR", sql_str)
            sql_str = re.sub("平片|普放|X片|X线片|X线", "DR", sql_str)
            df = pd.read_sql(sql_str, engine)
            break
        except Exception as e:
            error_message = f"""
            以上代码运行出错，请修改后再次输出。错误信息：
            ```
            {e.orig}
            ```
            """
            repair = messages.copy()
            repair.extend([
                AIMessage(content=sql_str),
                HumanMessage(content=error_message),
            ])
            parseStr = parser.invoke(llm.invoke(repair))
            mat = re.search(r'```sql(.*?)```', parseStr,
                            re.DOTALL | re.MULTILINE | re.I)
            if mat:
                sql_str = mat.group(1)
            else:
                sql_str = parseStr
            print(parseStr)
            print(f"SQL错误，正在进行第{n+1}次重试")
    # print("sql_str=",sql_str)
    # print(df)
    # print("正在尝试绘图")
    messages.extend([
        AIMessage(content=sql_str),
        HumanMessage(content=fig_prompt),
    ])
    # 输出解析
    result = llm.invoke(messages)
    parseStr = parser.invoke(result)
    # print(parseStr)
    try:
        mat = re.search(r"\s\[.*?\]", parseStr,
                        re.DOTALL | re.MULTILINE | re.I)
        if mat:
            figJson = mat.group(0)
        else:
            figJson = parseStr
        parseStr = json.loads(figJson)

    except:
        parseStr = []

    return sql_str, parseStr, df


#     return [examples[i] for i in most_similar_indices]
def clean_html(text):
    """清洗HTML标签"""
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text()
    return cleaned_text


def contains_chinese(s):
    """判断是否包含中文"""
    chinese_pattern = re.compile(r'[^\x00-\x7f]')
    return bool(chinese_pattern.search(s))


def clean_sentence(sentence: str):
    """清洗放射和病理文本"""
    sentence = clean_html(sentence)
    sentence = re.sub(r'[\t\xb2\b]', '', sentence).strip()
    sentence = re.sub(r'。+', '。', sentence).replace('"', '')
    sentence = re.sub(r' +', ' ', sentence)
    sentence = re.sub(r'-+', '-', sentence)
    for row in match_replace:
        if row['原始值'] is np.nan:
            continue
        if contains_chinese(row['原始值']):
            key_str = row['原始值']
        else:
            key_str = '(?<![A-Za-z])'+row['原始值']+'(?![A-Za-z])'
        if row['替换值'] is np.nan:
            sentence = re.sub(key_str, "", sentence, flags=re.I)
        else:
            sentence = re.sub(
                key_str, row['原始值']+"("+row['替换值']+")", sentence, flags=re.I)
    return sentence

@lru_cache(maxsize=1024)
def Match_result_LLM(radology_result: str, pathlogy_result: str)->dict:
    "判断放射和病理诊断是否相符"
    radology_result = clean_sentence(radology_result)
    pathlogy_result = clean_sentence(pathlogy_result)
    radology_analysis = get_orientation_position(radology_result)
    pathlogy_analysis = get_orientation_position(pathlogy_result)
    radology_matches = []
    for pathlogy in pathlogy_analysis:
        temp = [x for x in radology_analysis if ((x['position'] in pathlogy['partlist']) or
                (pathlogy['position'] in x['partlist']))
                and ((x['orientation'] == pathlogy['orientation']) or
                     ('双' in x['orientation']) or ('双' in pathlogy['orientation']) or
                     (x['orientation'] == '') or (pathlogy['orientation'] == ''))]
        if temp:
            radology_matches.extend([x['primary']
                                    for x in temp if x['ignore'] == False])
    if radology_matches == []:
        return {"result": "无法判断", "reason": "放射报告和病理报告人体器官无交集"}
    radology_matches = ",".join(set(radology_matches))
    # print("radology_matches:",radology_matches)
    prompt_str = match_prompt_file.format(
        radology_result=radology_matches, pathlogy_result=pathlogy_result)
    # print(prompt_str)
    messages = [
        SystemMessage(content="你是一个资深主任医师，审查年轻医生的放射诊断报告是否正确/no_think"),
        HumanMessage(content=prompt_str),
    ]
    # 输出解析
    start = time.time()
    response = llm.invoke(messages, config={"max_tokens": 150})
    token_count = response.response_metadata['token_usage']['completion_tokens']
    parseStr = response.content
    match = re.search("({[^}]*})", parseStr)
    if match:
        parseStr = match.group(1)
    for n in range(5):
        try:
            result = json.loads(re.sub("json|\r|\n|`", "", parseStr))
            match_result = result['result']
            reason = result['reason']
            break
        except:
            logger.error(f"格式错误，第{n+1}次重复")
            messages.append(AIMessage(content=parseStr))
            messages.append(HumanMessage(
                content="""把你的输出修正为严格的json格式，例如：{{"reason":"你判断的理由","result":"符合"}},不要在json之外有任何解释和评论"""))
            response = llm.invoke(messages, config={"max_tokens": 150})
            token_count = response.response_metadata['token_usage']['completion_tokens']
            parseStr = response.content
    # print(result)
    logger.info(f"放射-病理结果对比：output tokens:{token_count}, 耗时:{(time.time()-start):.2f}秒")
    return result

@lru_cache(maxsize=1024)
def Match_complex_result(Verification:str,
                        verification_type:str,
                        Pathology:str,
                        Clinical:str,
                        think:bool=False,
                        tool:bool=False)->dict:
    "判断待验证诊断和金标准诊断是否相符"
    result={"result": "", "reason": ""}
    Verification = clean_sentence(Verification)
    Pathology = clean_sentence(Pathology)
    start = time.time()
    if verification_type in ['CT',"MR","DX","MG","DR","MRI","磁共振","X线"]:
        radology_analysis = get_orientation_position(Verification)
        pathlogy_analysis = get_orientation_position(Pathology)
        radology_matches = []
        for pathlogy in pathlogy_analysis:
            temp = [x for x in radology_analysis if ((x['position'] in pathlogy['partlist']) or
                    (pathlogy['position'] in x['partlist']))
                    and ((x['orientation'] == pathlogy['orientation']) or
                        ('双' in x['orientation']) or ('双' in pathlogy['orientation']) or
                        (x['orientation'] == '') or (pathlogy['orientation'] == ''))]
            if temp:
                radology_matches.extend([x['primary']
                                        for x in temp if x['ignore'] == False])
        if radology_matches == []:
            result= {"result": "无法判断", "reason": f"{verification_type}报告和病理报告人体器官无交集"}
        elif radology_analysis==[]:
            result= {"result": "无法判断", "reason": f"{verification_type}报告信息不全"}
        elif radology_analysis==[]:
            result= {"result": "无法判断", "reason": "病理报告信息不全"}
        else:
            radology_matches = ",".join(set(radology_matches))
    else:
        radology_matches=Verification

    if result['result']!="无法判断":
        prompt_str = complex_match_prompt.format(
                verification_type=verification_type, 
                groundTruth_type='病理',
                Verification=radology_matches,
                groundTruth=Pathology)
        logger.info(f"{verification_type}-病理结果比对:工具={tool},推理={think}")
        if tool==False:
            messages = [
                SystemMessage(content="你是一个资深的主任医师，擅长质量控制，你的工作是审查年轻医生的诊断报告是否正确"),
                HumanMessage(content=prompt_str),
            ]
            # 输出解析
            response = llm.invoke(messages, config={"max_tokens": 150})
            token_count = response.response_metadata['token_usage']['completion_tokens']
            parseStr = response.content
        else:
            messages = [
                {"role": "system", "content":"""你是一个资深的主任医师，擅长质量控制，你的工作是审查年轻医生的诊断报告是否正确。
                    如果需要特定的医学知识（如疾病征象），请使用 `call_doctor_assistant` 工具查询。"""},
                {"role": "user", "content": prompt_str},
            ]
            # 输出解析
            response = execute_llm_step_openai(f"{verification_type}-病理结果比对:工具={tool},推理={think}", messages)
            parseStr = response["content"]
            
            token_count = len(parseStr)
        parseStr=re.sub(r'<think>.*?</think>', '', parseStr,flags=re.DOTALL)
        match = re.search("({[^}]*})", parseStr)
        if match:
            parseStr = match.group(1)
        for n in range(5):
            try:
                result = json.loads(repair_json(re.sub("json|\r|\n|`", "", parseStr)))
                break
            except:
                logger.error(f"格式错误，第{n+1}次重复")
                messages.append(AIMessage(content=parseStr))
                messages.append(HumanMessage(
                    content="""把你的输出修正为严格的json格式，例如：{{"reason":"你判断的理由","result":"符合"}},不要在json之外有任何解释和评论/no_think"""))
                response = llm.invoke(messages, config={"max_tokens": 150})
                token_count = response.response_metadata['token_usage']['completion_tokens']
                parseStr = response.content
        # print(result)
        logger.info(f"{verification_type}-病理结果比对:工具={tool},推理={think}，输出token:{token_count}, 耗时:{(time.time()-start):.2f}秒")
    #如果病理诊断无法判断且出院小结不为空，则进行出院小结比对
    if "判断" in result['result'] and Clinical.strip(): 
        prompt_str = complex_match_prompt.format(
            verification_type=verification_type, 
            groundTruth_type='出院小结',
            Verification=Verification,
            groundTruth=Clinical.strip())
        logger.info(f"{verification_type}-住院小结比对:工具={tool},推理={think}")
        if tool==False:
            messages = [
                SystemMessage(content="你是一个资深的主任医师，擅长质量控制，你的工作是判断诊断符合率"),
                HumanMessage(content=prompt_str),
            ]
            # 输出解析
            response = llm.invoke(messages, config={"max_tokens": 150})
            token_count = response.response_metadata['token_usage']['completion_tokens']
            parseStr = response.content
        else:
            messages = [
                {"role": "system", "content":"""你是一个资深的主任医师，擅长质量控制，你的工作是审查年轻医生的诊断报告是否正确。
                    如果需要特定的医学知识（如疾病征象），请使用 `call_doctor_assistant` 工具查询。"""},
                {"role": "user", "content": prompt_str},
            ]
            # 输出解析
            response = execute_llm_step_openai(f"{verification_type}-住院小结比对:工具={tool},推理={think}", messages)
            parseStr = response["content"]
            token_count = len(parseStr)
        parseStr=re.sub(r'<think>.*?</think>', '', parseStr,flags=re.DOTALL)
        match = re.search("({[^}]*})", parseStr)
        if match:
            parseStr = match.group(1)
        for n in range(5):
            try:
                result = json.loads(repair_json(re.sub("json|\r|\n|`", "", parseStr)))
                break
            except:
                logger.error(f"格式错误，第{n+1}次重复")
                messages.append(AIMessage(content=parseStr))
                messages.append(HumanMessage(
                    content="""把你的输出修正为严格的json格式，例如：{{"reason":"你判断的理由","result":"符合"}},不要在json之外有任何解释和评论/no_think"""))
                response = llm.invoke(messages, config={"max_tokens": 150})
                token_count = response.response_metadata['token_usage']['completion_tokens']
                parseStr = response.content
                parseStr=re.sub(r'<think>.*?</think>', '', parseStr,flags=re.DOTALL)
        # print(result)
        logger.info(f"{verification_type}-住院小结比对:工具={tool},推理={think}，输出token:{token_count}, 耗时:{(time.time()-start):.2f}秒")
    return result


if __name__ == '__main__':
    # 示例：测试SQL生成功能
    question = "统计最近三个月的MRI检查总人数"
    sql_str, fig_config, df = get_LLM_SQL(question)
    print(f"SQL: {sql_str}")
    print(f"图表配置: {fig_config}")
    print(f"数据:\n{df}")
