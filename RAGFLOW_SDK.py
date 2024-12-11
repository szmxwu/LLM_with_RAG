from ragflow_sdk import RAGFlow,Agent
from dotenv import load_dotenv
import os
import pandas as pd
from process_docs import pdf_page_to_image,split_pdf,split_docx,split_pptx
from multiprocessing import Pool
import asyncio
from threading import Thread
import time
import requests
# 加载.env文件中的环境变量
load_dotenv()
# 访问环境变量
API_KEY = os.getenv('API_KEY')
BASE_URL = os.getenv('BASE_URL')
RERANK_ID=os.getenv('RERANK_ID')
AGENT_ID=os.getenv('AGENT_ID')
ragflow=RAGFlow(api_key=API_KEY,base_url=BASE_URL)
conversation_ids=[]
CACHE_DIR = 'cache'  # 缓存目录
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def Create_dataset(name,description='',language="Chinese"):
    """新建知识库，并使用默认的向量库和通用解析方法，返回知识库ID

    Args:
        name (_type_): _description_
        description (str, optional): _description_. Defaults to ''.
        language (str, optional): _description_. Defaults to "Chinese".

    Returns:
        _type_: _description_
    """
    try:
        DataSet=ragflow.create_dataset(
            name=name,
            avatar = "",
            description = description,
            embedding_model = "BAAI/bge-large-zh-v1.5",
            language = language,
            permission = "me", 
            chunk_method = "naive",
            parser_config = None
        )
        return DataSet
    except:
        return None

def List_datasets(name=None):
    """列出所有的知识库

    Args:
        name (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    datalist=ragflow.list_datasets(
        page= 1, 
        page_size = 1000, 
        orderby = "create_time", 
        desc = True,
        id = None,
        name = name
        )
    return datalist


def upload_single_file(dataset, filename):
    # 提取扩展名
    file_extension = os.path.splitext(os.path.basename(filename))[1]
    if file_extension.lower() == '.pdf':
        document_list = split_pdf(filename)
    elif file_extension.lower() == '.pptx':
        document_list = split_pptx(filename)  
    elif file_extension.lower() == '.docx':
        document_list = split_docx(filename)
    else:
        if os.path.getsize(filename)>1024*1024*128:
            return "文件太大，无法处理"
        document_list=[filename]
    doc_blobs=[]
    for doc in document_list:
        doc_blobs.append({
            "display_name": os.path.basename(doc),
            "blob": open(doc, 'rb').read()
        })
    dataset.upload_documents(doc_blobs)


def Upload_documents(dataset_name:str,filename_list:list):
    """多进程上传文件
    
    Args:
        dataset_name (_type_): 知识库名称
        filename_list (_type_): 上传文件地址列表


    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    for filename in filename_list:
        file_extension = os.path.splitext(os.path.basename(filename))[1]
        if file_extension.lower() not in ['.pdf', '.docx', '.pptx','.xlsx',
                                          '.txt','.jpg','.jpeg','.png','.bmp']:
            return f"不支持的文件类型: {file_extension}"
    # 使用多进程并行上传文件
    with Pool(processes=os.cpu_count()) as pool:
        pool.starmap(upload_single_file, [(dataset[0], filename) for filename in filename_list])

def Download_document(doc_id,doc_name):
    """
    遍历所有知识库，下载文件到缓存目录
    """
    datasets=List_datasets()
    for dataset in datasets:
        doc = dataset.list_documents(id=doc_id)
        if len(doc)>0:
            open(f"{CACHE_DIR}/{doc_name}", "wb+").write(doc[0].download())
            return f"{CACHE_DIR}/{doc_name}"
        else:
            return f"can't find file {doc_name}"
def List_documents(dataset_name,doc_id=None):
    """列出知识库里的所有文档
        
    Args:
        dataset_name (_type_): 知识库名称
        keyword: 关键词，为空则返回所有文档
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset=dataset[0]
    return dataset.list_documents(
                        id=doc_id, 
                        page_size= 10000) 

def Delete_documents(dataset_name,doc_ids):
    """删除指定文档

    Args:
        doc_id (list): 文档id的列表
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset[0].delete_documents(ids=doc_ids)

def Parse_documents(dataset_name):
    """解析当前知识库内状态为unstart的文档

    Args:
        dataset_name (_type_): 知识库名
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    docs=List_documents(dataset_name)
    unParsed_docs=[x for x in docs if x.run=="UNSTART"]
    ids=[]
    for doc in unParsed_docs:
        file_extension = os.path.splitext(doc.name)[1]            
        if file_extension.lower()=='.pptx':
            doc.update([{"parser_config": {"chunk_token_count": 256}}, 
                        {"chunk_method": "presentation"}])
        elif file_extension.lower() in ['.jpg','.bmp','.png','.jpeg']:
            doc.update([{"parser_config": {"chunk_token_count": 256}}, 
                        {"chunk_method": "picture"}])
        elif file_extension.lower() in ['.xlsx','.csv']:
            doc.update([{"parser_config": {"chunk_token_count": 256}}, 
                        {"chunk_method": "table"}])
        else:
            doc.update([{"parser_config": {"chunk_token_count": 256}}, 
                        {"chunk_method": "naive"}])
        ids.append(doc.id) 
    dataset[0].async_parse_documents(ids)
    print("Async bulk parsing initiated.")

def Stop_parsing(dataset_name,document_ids):
    """停止解析文档

    Args:
        dataset_name (_type_): 知识库名
        document_ids (_type_): _description_

    Returns:
        _type_: _description_
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset[0].async_cancel_parse_documents(document_ids)
    print("Async bulk parsing cancelled.")

def Retrieve_chunks(question,dataset_name,filename='',top_n=8):
    """检索知识库，获得语义最接近的文本片段

    Args:
        question (_type_): 问题
        dataset_name (_type_): 知识库名
        filename:文件名
        top_k (_type_): 返回前k个结果
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset=dataset[0]
    docs=dataset.list_documents(page_size= 10000) 
    if filename!='':
        document_id=[d.id for d in docs if d.name==filename]
        if not document_id:
            print(f"未找到文档{filename}")
    else:
        document_id=None
    docs=ragflow.retrieve(question=question, dataset_ids=[dataset.id],
            document_ids=document_id,
            similarity_threshold=0.2, 
            rerank_id=RERANK_ID,
            vector_similarity_weight=0.5
            )
    if len(docs)>0:
        docs=docs[:top_n]
        result=[d.content.replace("\\n","").replace("\n","").replace("\'","'") for d in docs]
        return result
    else:
        return []
    


def Create_session(chat_name,user_id=None):
    """_summary_

    Args:
        chat_name (str, optional): 聊天助手的名字
        user_id (_type_, optional): 通过用户ID来区分不同用户的聊天记录.由于无登录功能，故采用浏览器cookie的方式来识别不同用户. 
            user_id= str(uuid.uuid4())
        如果user_id不在conversation_ids列表中，则创建一个新的会话，否则返回该用户原本的会话。
    Returns:
        _type_: _description_
    """
    assistant = ragflow.list_chats(name=chat_name)
    if not assistant: return f"can't find chat agent {chat_name}"
    assistant = assistant[0]
    session= [s['session'] for s in conversation_ids if s['user_id']==user_id]
    if not session:
        session = assistant.create_session()
        conversation_ids.append({'user_id':user_id, 'session':session})
        return session
    else:
        return session[0]
    
def Query_steam(question,chat_name,user_id=None):
    """向RAG提问并获取流式回答

    Args:
        question (str): 用户提出的问题
        chat_name (str): 聊天助手的名字
        user_id (_type_, optional): 用户ID. Defaults to None.

    yield:
        _type_: 流式回答

    """    
    session=Create_session(chat_name,user_id)
    # cont = ""
    # for ans in session.ask(question, stream=True):
    #     print(ans.content[len(cont):], end='', flush=True)
    #     cont = ans.content
    # print("/n")
    # return ans.reference
    return session.ask(question, stream=True)

def Show_all_datasets():
    """页面管理的首页，列出所有的知识库
    """
    datasets=List_datasets()
    result=[]
    for d in datasets:
        result.append({
            "知识库名":d.name,
            "文档数量":d.document_count,  
            "语言":d.language
        })
    return result


def Agent_chat(question):
    session = Agent.create_session(AGENT_ID,ragflow)    
    response=session.ask(question, stream=True)
    for ans in response:
        result=ans.content
    return result    
    
    
def Show_all_docs(dataset_name):
    """页面管理第二层，点开知识库后，列出指定知识库的所有文档
    """
    docs=List_documents(dataset_name)
    result=[]
    for d in docs:
        if d.run=="DONE":
            status="解析完成"
        elif d.run=="UNSTART":
            status="未解析"
        elif d.run=="RUNNING":
            status="解析中"
        else:
            status="解析失败"
        if d.size/1024/1024>=1:
            docsize="%.0fM" %(d.size/1024/1024)
        else:
            docsize="%.1fK" %(d.size/1024)
        if d.chunk_method== "naive":
            method="通用"
        elif d.chunk_method== "table":
            method="表格"
        elif d.chunk_method== "presentation":
            method="PPT"
        elif d.chunk_method== "picure":
            method="图片"
        else:
            method=d.chunk_method
        result.append({
            "文档名":d.name,
            "解析方式":method,
            "文件大小":docsize,
            "状态":status,
            "doc_id":d.id,
            "处理记录":d.progress_msg
        })
        return result

if __name__ == '__main__':
    question="上颌骨的常见病变有哪些？"
    chat_name="小影"
    assistant = ragflow.list_chats(name=chat_name)
    assistant = assistant[0]
    session = assistant.create_session()    

    print("\n==================== Miss R =====================\n")
    print("Hello. What can I do for you?")

    while True:
        question = input("\n==================== User =====================\n> ")
        print("\n==================== Miss R =====================\n")
        
        cont = ""
        for ans in session.ask(question, stream=True):
            print(ans.content[len(cont):], end='', flush=True)
            cont = ans.content
        print(ans.reference)
