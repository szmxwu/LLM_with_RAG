from RAGFLOW_SDK import Download_document, List_documents, Upload_documents, List_datasets, Create_dataset, Delete_documents, Parse_documents, Stop_parsing, Retrieve_chunks, Query_steam, BASE_URL, Agent_chat, Show_all_datasets, Show_all_docs
from process_docs import pdf_page_to_image
import re
import os
import time
from threading import Thread
import json
import subprocess
import uuid
import gradio
import re
import pandas as pd
import numpy as np
import warnings
from pprint import pprint
from bs4 import BeautifulSoup
import sqlalchemy as sql
from keyword_extraction import get_orientation_position
import configparser
from sklearn.metrics.pairwise import cosine_similarity
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from langchain.prompts import load_prompt
from langchain_openai import ChatOpenAI
import ast
# from langchain.memory import ConversationTokenBufferMemory
# from langchain.chains import ConversationChain
from langchain_community.embeddings import XinferenceEmbeddings
from dotenv import load_dotenv
warnings.filterwarnings('ignore')
load_dotenv()
# 访问环境变量
PATH_MATCH_REPLACE_FILE = 'documents/match_replace.xlsx'
LLM_NAME = os.getenv('LLM_NAME')
XINFERENCE = os.getenv('XINFERENCE')
ODBC = os.getenv('ODBC')
RERANK_ID = os.getenv('RERANK_ID')
EMBEDDING = os.getenv('EMBEDDING')
CACHE_DIR = 'cache'
conf = configparser.ConfigParser()
conf.read('system_config.ini', encoding="utf-8")
# connectionString = conf.get("sqlQuery","connectionString")
# inteEngine = sql.create_engine(connectionString)

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
    api_key="EMPTY",
)


embedder = XinferenceEmbeddings(
    server_url=XINFERENCE,
    model_uid=EMBEDDING
)

# 建立大模型临时记忆
history_messages = []


# 读取预设提示词
sql_prompt_file = load_prompt("prompt/sql_prompt.json", encoding='utf-8')
match_prompt_file = load_prompt(
    "prompt/match_prompt_template.json", encoding='utf-8')
# fig_prompt_file = load_prompt("prompt/fig_prompt_template.json",encoding='utf-8')
judge_prompt_file = load_prompt(
    "prompt/judge_prompt_template.json", encoding='utf-8')
with open('prompt/fig_prompt.txt', 'r', encoding='utf-8') as file:
    fig_prompt = file.read()


def Query(question, chat_name, user_id=None):
    """调用Query_steam并等待流式回答完全结束，返回两部分结果：
       第一部分是在流式回答的过程中，实时返回Query_steam函数的输出；
       第二部分是等待流式回答完全结束后，返回json格式的完整回答。

    Args:
        question (str): 用户提出的问题
        chat_name (str): 聊天助手的名字
        user_id (str, optional): 用户ID. Defaults to None.


    """
    answer = Query_steam(question, chat_name, user_id)
    cont = ""
    for ans in answer:
        if ans.content[len(cont):] not in cont:
            print(ans.content[len(cont):], end='', flush=True)
        cont = ans.content
    # 根据回答内容，生成病例检索关键词
    Thread(target=generate_probe, args=(ans.content,)).start()
    # 保留被大模型选用的引文或者包含图片的
    print("\n")
    reference_index = re.findall("##(\d)\$\$", ans.content)
    if reference_index:
        reference_index = [int(x) for x in reference_index]
    reference = []
    for index, ref in enumerate(ans.reference):
        if (index in reference_index) or len(ref["image_id"]) > 0:
            reference.append(ref)
    send_reference(reference)


def generate_probe(answer):
    """
    生成追问关键词，用于查询病例库
    """
    with open('prompt/probe_prompt.txt', 'r', encoding='utf-8') as file:
        probe_prompt = file.read()
    probe_prompt = probe_prompt.replace("{answer}", answer)
    parser = StrOutputParser()
    keywords = parser.invoke(llm.invoke(probe_prompt))
    # 将关键词返回显示在界面的回答下方，用户可点击关键词进行搜索
    print("相关病例关键词:",keywords)
    print(search_case(keywords))
    return keywords


def search_case(keywords):
    """
    根据关键词搜索病例库
    弹出新的页面，用列表+图像展示病例，注意文档中的图片URL是相对路径，需要转换为绝对路径
    """
    cases = Retrieve_chunks(keywords, '病例', "", 20)
    result = []
    for case in cases:
        result.append(f"<h3>{case.document_name}</h3><br>case.content")
    return result


def send_reference(reference_chunks):
    """发送参考文献

    Args:
        reference_chunks (_type_): _description_

    Returns:
        _type_: _description_
    """
    if not reference_chunks:
        return None
    # 合并同一文件的多个页码
    merged_docs = {}
    for doc in reference_chunks:
        try:
            doc['page'] = list(set([int(x[0]) for x in doc['positions']]))
        except:
            doc['page'] = []
        if doc['document_id'] not in merged_docs or doc['page'] == []:
            merged_docs[doc['document_id']] = doc
        else:
            merged_docs[doc['document_id']]['page'].extend(doc['page'])
            merged_docs[doc['document_id']]['page'] = sorted(
                list(set(merged_docs[doc['document_id']]['page'])))
    reference_chunks = [value for value in merged_docs.values()]
    references = "### 参考文献\n"
    index = 1
    for chunk in reference_chunks:
        extension = os.path.splitext(chunk['document_name'])[1]
        extension = extension[1:]
        if chunk['document_id'] not in references:
            file_extension = os.path.splitext(
                os.path.basename(chunk['document_name']))[1]
            if file_extension in ['.xlsx', '.xls', '.ppt', '.pptx']:
                # 以上文件类型为下载链接
                references += f"- [{index}] [{chunk['document_name']}]({BASE_URL}/v1/document/get/{chunk['document_id']}){chunk['page']}\n"
            else:
                # 以上文件类型为预览链接
                references += f"- [{index}] [{chunk['document_name']}]({BASE_URL}/document/{chunk['document_id']}?ext={extension}&prefix=document){chunk['page']}\n"
            index += 1
        if extension == "pdf":
            Thread(target=get_pdf_content, args=(
                chunk['document_id'],
                chunk['document_name'],
                chunk['page']
            )).start()
        elif extension == "pptx":
            Thread(target=get_ppt_content, args=(
                chunk['document_id'],
                chunk['document_name'],
                chunk['page']
            )).start()
        else:
            Thread(target=get_other_content, args=(
                chunk['document_name'],
                chunk['content'],
                chunk['image_id']
            )).start()
    print(references)


def get_pdf_content(doc_id, doc_name, page):
    exists, filepath = check_cache(doc_name)
    if not exists:
        print("Downloading file...")
        filepath = Download_document(doc_id, doc_name)
    else:
        print(f"{doc_name} is in cache")
    for p in page:
        # 把页面转化为图片
        img_path = pdf_page_to_image(filepath, p)
        # 发送图片到gradio对话框
        print(img_path)


def get_ppt_content(doc_id, doc_name, page):
    exists, filepath = check_cache(doc_name)
    if not exists:
        print("Downloading file...")
        filepath = Download_document(doc_id, doc_name)
    else:
        print(f"{doc_name} is in cache")
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
    for p in page:
        # 把页面转化为图片
        img_path = pdf_page_to_image(filepath, p)
        # 发送图片到gradio对话框
        print(img_path)


def get_other_content(filename, content_ltks, img_id):
    """处理其他类型引文的显示"""
    time.sleep(0.3)
    content_ltks = content_ltks.replace("。", "。<br>")
    content = f"<h3>{filename}</h3><br>{content_ltks}<br>"
    # 显示图片，特别重要
    if img_id:
        content += f'<img src="{BASE_URL}/v1/document/image/{img_id}" alt="图片" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
        # 这里地址拼接有问题，但是文档里没有找到相关内容
    # 发送HTML到gradio对话框
    print(content)


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


def Match_result_LLM(radology_result: str, pathlogy_result: str):
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
        SystemMessage(content="你是一个医学助理，帮助用户处理医学检查数据"),
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
            print(f"格式错误，第{n+1}次重复")
            messages.append(AIMessage(content=parseStr))
            messages.append(HumanMessage(
                content="""把你的输出修正为严格的json格式，例如：{{"reason":"你判断的理由","result":"符合"}},不要在json之外有任何解释和评论"""))
            response = llm.invoke(messages, config={"max_tokens": 150})
            token_count = response.response_metadata['token_usage']['completion_tokens']
            parseStr = response.content
    # print(result)
    print("output tokens:", token_count, "耗时:%.1f秒" % (time.time()-start))
    return result




if __name__ == '__main__':
    question = "支气管肺发育不良诊断标准"
    chat_name = "小影"
    dataset_name = "放射学"
    # print(Show_all_docs(dataset_name))
    Query(question, chat_name)
    # sql_question="统计2024年11月CT检查类型中，各机器检查的人次数量"
    # result=Retrieve_chunks(sql_question,'SQL',top_n=2)

    # print([r.replace("\\n","") for r in result])
    # result=get_LLM_SQL(sql_question)
    # print(result)
    # question="统计最近三个月的MRI检查总人数"
    # print(get_LLM_SQL(question))
    # sql_question="自2000年以来美国、加拿大、墨西哥的人口情况"
    # print(Agent_chat(sql_question))
    # filename_list=['F:\\big_pptx\\髋关节常见病变MR诊断.pptx']
    # filename_list=["H:\\output_directory\\pdf\\肿瘤影像诊断图谱.pdf"]
    # Upload_documents("放射学",filename_list)
    # Parse_documents("放射学")
#     radology_result="""
# 1.双肺多发磨玻璃、实性结节，大致同前相仿，随访；前上纵隔小结节基本同前相仿。
# 2.右肾切除术后改变，术区未见明确复发征象；腹膜后及肠系膜见数枚稍大淋巴结，以上均同前相仿；盆腔少量积液，较前略增多。
# 3.附见甲状腺密度不均匀伴低密度结节，请结合专科检查。
# """
#     pathlogy_result="""
# 2024-09-02:样本所测HPV基因所有亚型均为阴性。
# 2024-09-02:无上皮内病变或恶性病变（NILM）。


# """
#     result=Match_result_LLM(radology_result,pathlogy_result)
#     pprint(result)
