from ragflow_sdk import RAGFlow, Agent
from dotenv import load_dotenv
import os
from process_docs import convert_pptx, split_pdf
from multiprocessing import Pool
import urllib.request
from io import BytesIO
import requests

# 加载.env文件中的环境变量
load_dotenv()
# 访问环境变量
API_KEY = os.getenv('API_KEY')
BASE_URL = os.getenv('BASE_URL')
RERANK_ID = os.getenv('RERANK_ID')
AGENT_ID = os.getenv('AGENT_ID')
EMBEDDING= os.getenv('EMBEDDING')

# 外部重排序服务配置（Xinference）
RERANK_URL = os.getenv('RERANK_URL', 'http://192.0.0.188:9997/v1')
RERANK_MODEL = os.getenv('RERANK_MODEL', 'bge-reranker-v2-m3')


class ExternalReranker:
    """外部重排序服务客户端（基于Xinference）"""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or RERANK_URL
        self.model = model or RERANK_MODEL
        # 确保URL以/v1结尾
        if not self.base_url.endswith('/v1'):
            self.base_url = self.base_url.rstrip('/') + '/v1'

    def rerank(self, query: str, documents: list, top_n: int = 8) -> list:
        """
        对文档进行重排序

        Args:
            query: 查询问题
            documents: 文档列表，每个文档包含content属性
            top_n: 返回前n个结果

        Returns:
            重排序后的文档列表
        """
        if not documents:
            return documents

        # 提取文档内容
        docs_text = []
        for doc in documents:
            content = getattr(doc, 'content', '')
            if content:
                docs_text.append(content)

        if not docs_text:
            return documents[:top_n]

        try:
            # 调用Xinference重排序API
            response = requests.post(
                f"{self.base_url}/rerank",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "query": query,
                    "documents": docs_text,
                    "top_n": top_n,
                    "return_documents": False  # 只返回索引和分数
                },
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            # 根据重排序结果重新排列文档
            reranked_docs = []
            for item in result.get('results', []):
                idx = item.get('index', 0)
                if 0 <= idx < len(documents):
                    doc = documents[idx]
                    # 添加重排序分数
                    doc.rerank_score = item.get('relevance_score', 0)
                    reranked_docs.append(doc)

            return reranked_docs if reranked_docs else documents[:top_n]

        except Exception as e:
            print(f"外部重排序失败: {e}，使用原始排序")
            return documents[:top_n]


# 初始化重排序客户端
reranker = ExternalReranker()
try:
    MAX_FILE_UPLOAD=int(os.getenv('MAX_FILE_UPLOAD'))
except:
    MAX_FILE_UPLOAD=1280
ragflow = RAGFlow(api_key=API_KEY, base_url=BASE_URL)
conversation_ids = []
CACHE_DIR = 'cache'  # 缓存目录
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


def Create_dataset(name, description='', language="Chinese"):
    """新建知识库，并使用默认的向量库和通用解析方法，返回知识库ID

    Args:
        name (_type_): 知识库名
        description (str, optional): 知识库描述.
        language (str, optional): 语言. Defaults to "Chinese".

    Returns:
        _type_: dataset
    """
    try:
        DataSet = ragflow.create_dataset(
            name=name,
            avatar="",
            description=description,
            embedding_model=EMBEDDING,
            language=language,
            permission="me",
            chunk_method="naive",
            parser_config=None
        )
        return DataSet
    except:
        return None


def List_datasets(name=None,id=None):
    """列出所有的知识库

    Args:
        name (_type_, optional): _description_. Defaults to None.

    Returns:
        _type_: _description_
    """
    datalist = ragflow.list_datasets(
        page=1,
        page_size=1000,
        orderby="create_time",
        desc=True,
        id=id,
        name=name
    )
    return datalist


async def upload_single_file(dataset, file):
    """分拆并上传单个文件

    Args:
        dataset (string): 知识库名
        file (list): 文件列表

    Returns:
        _type_: _description_
    """
    # 提取扩展名
    file_extension = os.path.splitext(os.path.basename(file.filename))[1]
    if file_extension.lower() == '.pdf':
        #pdf进行切割
        document_list = split_pdf(file)
    else:
        if file.size > 1024*1024*MAX_FILE_UPLOAD:
            return "文件太大，无法处理"
    if file_extension.lower() == '.pptx':
        #ppt尽可能转化为word
        document_list = convert_pptx(file)
    else:
        document_list = [file]
    doc_blobs = []
    print("list=",document_list)
    for doc in document_list:
        if isinstance(doc,str):
            content=open(doc, 'rb').read()
        else:
            content=await file.read()
            content=BytesIO(content)
        doc_blobs.append({
            "displayed_name": doc.filename,
            "blob": content
        })
    print("正在上传:",document_list)
    return dataset.upload_documents(doc_blobs)


async def Upload_documents(dataset_name: str, file_list: list):
    """多进程上传文件

    Args:
        dataset_name (_type_): 知识库名称
        filename_list (_type_): 上传文件地址列表


    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    # 使用多进程并行预处理及上传文件
    # with Pool(processes=4) as pool:
    #     pool.starmap(upload_single_file, [
    #                  (dataset[0], file) for file in file_list])
    for file in file_list:
        upload_single_file(dataset[0], file)


def Download_document(doc_id, doc_name):
    """
    下载文件到缓存目录
    """
    url=f"{BASE_URL}/v1/document/get/{doc_id}"
    try:
        urllib.request.urlretrieve(url, f"{CACHE_DIR}/{doc_name}")
        # print("下载完成！")
        return f"{CACHE_DIR}/{doc_name}"
    except Exception as e:
        return "下载失败:", e
    


def List_documents(dataset_name, keyword=None, doc_id=None):
    """列出知识库里的所有文档

    Args:
        dataset_name (_type_): 知识库名称
        keyword: 关键词，为空则返回所有文档
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset = dataset[0]
    return dataset.list_documents(
        keywords=keyword,
        id=doc_id,
        page_size=10000)


def Delete_documents(dataset_name, doc_id):
    """删除指定文档

    Args:
        doc_id (list): 文档id的列表
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset[0].delete_documents(ids=[doc_id])


def Parse_documents(dataset_name,doc_id=None):
    """解析当前知识库内状态为unstart的文档

    Args:
        dataset_name (_type_): 知识库名
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    if doc_id is not None:
        try:
            dataset[0].async_parse_documents(doc_id)
        except:
            return f"doc_id={doc_id} parse error"
    else:
        docs = List_documents(dataset_name)
        ids = [x.id for x in docs if x.run == "UNSTART"]
        dataset[0].async_parse_documents(ids)
        return "Async bulk parsing initiated"


def Stop_parsing(dataset_name, document_ids):
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


def Retrieve_chunks(question, dataset_name, filename='', top_n=8, use_rerank=True):
    """检索知识库，获得语义最接近的文本片段

    Args:
        question (_type_): 问题
        dataset_name (_type_): 知识库名
        filename:文件名
        top_n (_type_): 返回前n个结果
        use_rerank: 是否使用外部重排序服务
    """
    dataset = List_datasets(name=dataset_name)
    if not dataset:
        return f"can't find dataset {dataset_name}"
    dataset = dataset[0]
    docs = dataset.list_documents(page_size=10000)
    if filename != '':
        document_id = [d.id for d in docs if d.name == filename]
        if not document_id:
            print(f"未找到文档{filename}")
    else:
        document_id = None

    # 第一步：使用RAGFlow进行向量检索（获取较多结果用于重排序）
    retrieve_top_n = top_n * 3 if use_rerank else top_n  # 如果重排序，多取一些结果
    docs_retrieve = ragflow.retrieve(
        question=question,
        dataset_ids=[dataset.id],
        document_ids=document_id,
        similarity_threshold=0.2,
        vector_similarity_weight=1.0  # 纯向量检索
    )

    if len(docs_retrieve) == 0:
        return []

    # 第二步：使用外部重排序服务优化结果
    if use_rerank and len(docs_retrieve) > 1:
        try:
            docs_retrieve = reranker.rerank(question, docs_retrieve, top_n=top_n)
        except Exception as e:
            print(f"重排序失败: {e}，使用向量检索结果")
            docs_retrieve = docs_retrieve[:top_n]
    else:
        docs_retrieve = docs_retrieve[:top_n]

    # 补充文档名称
    for d in docs_retrieve:
        if d.document_name == '':
            name = [x.name for x in docs if x.id == d.document_id]
            if name:
                d.document_name = name[0]

    return docs_retrieve


def Create_session(chat_name, user_id=None):
    """_summary_

    Args:
        chat_name (str, optional): 聊天助手的名字
        user_id (_type_, optional): 通过用户ID来区分不同用户的聊天记录 
            user_id= str(uuid.uuid4())
        如果user_id不在conversation_ids列表中，则创建一个新的会话，否则返回该用户原本的会话。
    Returns:
        _type_: _description_
    """
    assistant = ragflow.list_chats(name=chat_name)
    if assistant==[]:
        return f"can't find chat agent {chat_name}"
    assistant = assistant[0]
    session=None
    if user_id is not None:
        sessions = [s['session']
                for s in conversation_ids if s['user_id'] == user_id]
        if sessions!=[]:
            session=sessions[0]
    if session is None:
        session = assistant.create_session()
        conversation_ids.append({'user_id': user_id, 'session': session})
    return session


def Query_steam(question, chat_name, user_id=None):
    """向RAG提问并获取流式回答

    Args:
        question (str): 用户提出的问题
        chat_name (str): 聊天助手的名字
        user_id (_type_, optional): 用户ID. Defaults to None.

    yield:
        _type_: 流式回答

    """
    session = Create_session(chat_name, user_id)
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
    datasets = List_datasets()
    result = []
    for d in datasets:
        result.append({
            "知识库名": d.name,
            "文档数量": d.document_count,
            "语言": d.language
        })
    return result


def Agent_chat(question):
    session = Agent.create_session(AGENT_ID, ragflow)
    response = session.ask(question, stream=True)
    for ans in response:
        result = ans.content
    return result


def Show_all_docs(dataset_name:str,keyword:str=None,doc_id=None):
    """知识库管理，列出指定知识库的所有文档
    """
    docs = List_documents(dataset_name,keyword,doc_id)
    result = []
    for d in docs:
        if d.run == "DONE":
            status = "解析完成"
        elif d.run == "UNSTART":
            status = "未解析"
        elif d.run == "RUNNING":
            status = "解析中"
        else:
            status = "解析失败"
        if d.size/1024/1024 >= 1:
            docsize = "%.0fM" % (d.size/1024/1024)
        else:
            docsize = "%.1fK" % (d.size/1024)
        if d.chunk_method == "naive":
            method = "通用"
        elif d.chunk_method == "table":
            method = "表格"
        elif d.chunk_method == "presentation":
            method = "PPT"
        elif d.chunk_method == "picure":
            method = "图片"
        else:
            method = d.chunk_method
        result.append({
            "name": d.name,
            "parseMethod": method,
            "size": docsize,
            "status": status,
            "doc_id": d.id,
            "progress": "%.0f%%" %(d.progress*100),
            'url':f"{BASE_URL}/v1/document/get/{d.id}"
        })
    return result

def init_chat_agent(hospitalID:str,hospitalName:str):
    """为每个医院创建独立的聊天助手

    Args:
        hospitalID (str): 医院组织机构编码
    """
    global data_name,chat_agent_name
    data_name="H"+hospitalID
    chat_agent_name="C"+hospitalID
    #查询私有知识库是否存在
    private_dataset = List_datasets(name=data_name)
    if private_dataset:
        return data_name,chat_agent_name
    
    try:
        #不存在则创建私有知识库和聊天助手
        private_dataset=Create_dataset(data_name, 
                            description=hospitalName, 
                            language="Chinese")
        public_datasets = List_datasets(name="放射学")
        if public_datasets:
            public_datasets=public_datasets[0]
        ragflow.create_chat(
                name=chat_agent_name, 
                dataset_ids = [private_dataset.id,public_datasets.id])
        return data_name,chat_agent_name
    except:
        return "",""
    
def List_chunks(dataset_id:str,doc_id:str):
    datasets=List_datasets(id=dataset_id)
    if datasets:
        data=datasets[0]
        doc=data.list_documents(id=doc_id)
        if doc:
            return doc[0].list_chunks(page_size=10000)
            

if __name__ == '__main__':
    # question = "上颌骨的常见病变有哪些？"
    # chat_name = "小影"
    # assistant = ragflow.list_chats(name=chat_name)
    # assistant = assistant[0]
    # session = assistant.create_session()

    # print("\n==================== Miss R =====================\n")
    # print("Hello. What can I do for you?")

    # while True:
    #     question = input(
    #         "\n==================== User =====================\n> ")
    #     print("\n==================== Miss R =====================\n")

    #     cont = ""
    #     for ans in session.ask(question, stream=True):
    #         print(ans.content[len(cont):], end='', flush=True)
    #         cont = ans.content
    #     print(ans.reference)
    # filename_list = []
    # directory="H:\\output_directory\\other"
    # # # 遍历指定路径下所有的文件和目录
    # for root, _, files in os.walk(directory):
    #     # 每次迭代时，root是当前的目录路径，而files是该目录下的文件列表
    #     for file in files:
    #         # 获取文件的完整路径（绝对路径）
    #         file_path = os.path.join(root, file)
    #         # 将路径添加到列表中
    #         filename_list.append(file_path)
    # Upload_documents("放射学", filename_list)
    # keywords="cerebellar cortex white matter cerebellar nuclei cerebellum compartments"
    # Retrieve_chunks(keywords, '病例', "", 10)
    result=Show_all_docs("放射学",keyword="放射")
    print([d['name'] for d in result])
