# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
import threading
import uvicorn
from llm_func import *
from threading import Thread
import uuid
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.staticfiles import StaticFiles
import logging
import logging.config
from typing import Dict

# WebSocket客户端管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

# 日志配置字典
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} - {levelname} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
    },
    'loggers': {
        'uvicorn': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'fastapi': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# 配置日志
logging.config.dictConfig(LOGGING)

manager = ConnectionManager()
app = FastAPI(docs_url=None, redoc_url=None, title='放射大模型服务', version='0.0.1',
            description="""<b>大模型接口文档，提供以下接口:</b><br>
                get_uuid:获得临时用户id <br>
                Coincidence:放射诊断与病理诊断的符合判断 <br>
                rag_ask:放射决策大模型问答 <br>
                list_case:图片病例数据库检索<br>
                upload_folder：上传包含文档的文件夹<br>
                del_docs:删除指定文档
            """)

app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket路由
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )

@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


async def Query(question, chat_name, user_id=None):
    """调用Query_steam并等待流式回答完全结束，返回两部分结果：
       第一部分是在流式回答的过程中，实时返回Query_steam函数的输出；
       第二部分是等待流式回答完全结束后，返回json格式的完整回答。

    Args:
        question (str): 用户提出的问题
        chat_name (str): 聊天助手的名字
        user_id (str, optional): 通过get_uuid获得的对话ID 


    """
    # 第一阶段，流式返回回答
    answer = Query_steam(question, chat_name, user_id)
    cont = ""
    for ans in answer:
        if ans.content[len(cont):] not in cont:
            print(ans.content[len(cont):], end='', flush=True)
            yield ans.content[len(cont):]
        cont = ans.content

    # 第二阶段，生成参考文献列表
    ## 保留被大模型选用的引文或者包含图片的引文
    reference_index = re.findall("##(\d)\$\$", ans.content)
    if reference_index:
        reference_index = [int(x) for x in reference_index]
    reference_chunks = []
    for index, ref in enumerate(ans.reference):
        if (index in reference_index) or len(ref["image_id"]) > 0:
            reference_chunks.append(ref)
    ## 合并同一文件的多个页码
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
    references = "\n### 参考文献\n"
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
    ## 返回参考文献列表       
    print(references) 
    yield references 
    # 第三阶段 异步获取引文截图或引文片段
    Thread(target=send_reference,args=(reference_chunks,user_id)).start()      
    # 第四阶段，根据回答内容，生成病例检索关键词
    keywords=generate_probe(ans.content)
    yield f"\n{keywords}"


def send_reference(reference_chunks, user_id: str):
    """发送参考文献

    Args:
        reference_chunks (_type_): 参考文献块
        user_id (str): 用户ID
    """
    if not reference_chunks:
        return None

    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def _send_all():
            for chunk in reference_chunks:
                extension = os.path.splitext(chunk['document_name'])[1]
                extension = extension[1:]
                if extension == "pdf":
                    content = get_pdf_content(chunk['document_id'], chunk['document_name'], chunk['page'])
                    if content:
                        await manager.send_message(json.dumps({
                            'type': 'pdf',
                            'name': chunk['document_name'],
                            'content': content
                        }), user_id)
                elif extension == "pptx":
                    content = get_ppt_content(chunk['document_id'], chunk['document_name'], chunk['page'])
                    if content:
                        await manager.send_message(json.dumps({
                            'type': 'ppt',
                            'name': chunk['document_name'],
                            'content': content
                        }), user_id)
                else:
                    content = get_other_content(chunk['document_name'], chunk['content'], chunk['image_id'])
                    if content:
                        await manager.send_message(json.dumps({
                            'type': 'other',
                            'name': chunk['document_name'],
                            'content': content
                        }), user_id)
        loop.run_until_complete(_send_all())
        loop.close()
    
    threading.Thread(target=run_async).start()


@app.get('/get_uuid')
def get_uuid():
    """获得一个新的uuid，用来填入rag_ask，以区分不同的对话session

    Returns:
        str: 16位的随机UUID
    """
    return uuid.uuid4()

@app.post('/Coincidence')
def Coincidence(radology_result: str, pathlogy_result: str):
    """判断放射和病理诊断是否相符<br>
    输入格式<br>
      radology_result：放射诊断<br>
      pathlogy_result：病理诊断<br>
    返回格式：{"reason":"判断理由","result":"符合/基本符合/不符合"}"""
    return Match_result_LLM(radology_result, pathlogy_result)

@app.post('/rag_ask')
async def rag_ask(question:str, user_id:str):
    """流式返回放射决策大模型的回答

    Args:
        question (str): 用户提出的问题
        user_id:用户ID
    """
    return StreamingResponse(Query(question=question, chat_name='小影', user_id=user_id),
                             media_type='text/plain')

@app.post('/list_case')
def list_case(keywords):
    """返回病例库中的相关病例图片

    Args:
        keywords (_type_): 病例关键词，来源于rag_ask返回的最后一行
    """
    return search_case(keywords)

@app.post("/list_docs")
def list_docs(dataset_name):
    """列出指定知识库的所有文档

    Args:
        dataset_name (_type_): 知识库名称
    """
    Show_all_docs(dataset_name)



@app.post("/del_docs")
def Del_docs(dataset_name, doc_ids):
    """ 删除指定文档

    Args:
        doc_id (list): 文档id的列表
    """
    Delete_documents(dataset_name, doc_ids)

@app.post("/upload_folder")
def upload_folder(dataset_name:str, directory:str):
    """上传指定文件夹里的所有文件，并解析

    Args:
        dataset_name (str): 知识库名称
        directory (str): 文件夹地址
    """
    filename_list = []
    # # 遍历指定路径下所有的文件和目录
    for root, _, files in os.walk(directory):
        # 每次迭代时，root是当前的目录路径，而files是该目录下的文件列表
        for filename in files:
            # 获取文件的完整路径（绝对路径）
            file_extension = os.path.splitext(os.path.basename(filename))[1]
            if file_extension.lower() not in ['.pdf', '.docx', '.pptx', '.xlsx','.doc','xls','ppt',
                                          '.txt', '.jpg', '.jpeg', '.png', '.bmp']:
                continue
            file_path = os.path.join(root, filename)
            # 将路径添加到列表中
            filename_list.append(file_path)
    #上传文件列表
    Upload_documents("放射学", filename_list)
    #解析所有上传文件
    Parse_documents(dataset_name)
    
if __name__ == "__main__":
    uvicorn.run('agent_server:app', host='0.0.0.0', port=8080)
