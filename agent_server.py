# -*- coding: utf-8 -*-
from fastapi import FastAPI, WebSocket, WebSocketDisconnect,File,UploadFile
from fastapi.responses import StreamingResponse
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import asyncio
import uvicorn
from llm_func import *
from knownlege_agent import KnowledgeAgent,OptimizedProcessor
from simple_agent import ChatAgent
import uuid
import re
import os
# from functools import lru_cache
from pydantic import BaseModel, Field
from markdown import markdown
from RAGFLOW_SDK import init_chat_agent, Query_steam,upload_single_file,Parse_documents
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from io import BytesIO
import logging.config
from typing import Dict
from dotenv import load_dotenv
load_dotenv()
DEFAUT_DATA = os.getenv('DEFAUT_DATA')
DEFAUT_CASE= os.getenv('DEFAUT_CASE')
ENDPOINT_IP=os.getenv('ENDPOINT_IP')
try:
    MAX_FILE_UPLOAD=int(os.getenv('MAX_FILE_UPLOAD'))
except:
    MAX_FILE_UPLOAD=2048
# 医院私有知识库
data_name = ""
# 医院私有聊天助手
chat_agent_name = ""
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
            'format': '{asctime} - {levelname} - {module}:{lineno} - {message}',
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
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'AgentServer.log',
            'maxBytes': 100 * 1024 * 1024,  # 100MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8'
        }
    },
    'loggers': {
        'uvicorn': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False
        },
        'fastapi': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO'
    }
}

# 配置日志
logging.config.dictConfig(LOGGING)
logger = logging.getLogger(__name__)

manager = ConnectionManager()
app = FastAPI(docs_url=None, redoc_url=None, title='放射质控大模型服务', version='0.0.2',
              description="""<b>智能体接口文档，提供以下接口:</b><br>
                get_uuid:获得临时用户id <br>
                Coincidence:放射诊断与病理诊断的符合判断 <br>
                rag_ask:放射决策大模型问答 <br>
                patient_summury：总结患者信息并给出要点 <br>
                list_case:图片病例数据库检索<br>
                upload_folder：上传包含文档的文件夹<br>
                del_docs:删除指定文档<br>
                <b>其他配置:.env</b><br>
                    xinference:运行3个模型：llm，embedding，rerank<br>
                    ragflow(BASE_URL):提供本地知识库服务<br>
                    HOST_IP：本服务运行的地址和端口<br>
                    ENDPOINT_IP：前段web服务的地址和端口<br>
            """)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

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

simple_chatbot=ChatAgent()

class AskRequest(BaseModel):
    """RAG查询数据结构.<br>
    question:提出的问题 string<br>
    user_id:对话ID string<br>
    chat_name：聊天助手的名字 string<br>
    """

    question: str = Field(title="提出的问题", example="肝癌的发生机制")
    user_id: str = Field(title="对话ID", example="xxxx-xxxx-xxx1-xxx1")
    chat_name: str = Field(title="聊天助手", example='小影')

class Diagnosis(BaseModel):
    """放射诊断和病理诊断<br>
    radology_result（string）:放射报告的诊断结论 <br>
    pathlogy_result（string）:病理报告的诊断结论 <br>
    """

    radology_result: str = Field(title="放射报告的诊断结论", example="""
                                 考虑前列腺癌，PI-RADS 5；向上突入膀胱，并累及左输尿管膀胱壁内段致左侧输尿管积水；膀胱左后方结节，考虑转移。
                                 髋臼、骨盆骨质以及双侧股骨头多发骨转移。盆腔内髂内动脉旁可见多个小淋巴结，性质待定。
                                 """)
    pathlogy_result: str = Field(title="病理报告的诊断结论", example="""
                                 2024-05-27:1.（前列腺1）前列腺腺泡性腺癌，gleason评分4+4=8分，WHO/ISUP前列腺分级分组4组，可见神经侵犯，未见脉管内癌栓，
                                 癌组织占该针前列腺穿刺组织60%，免疫组化结果：P504S(+)、P63(-)、34βE12(-)、PSA(+)、PSAP(+)、AR(+)、P53(-)、Ki-67(2%+)。
                                 2.（前列腺2）前列腺腺泡性腺癌，gleason评分4+4=8分，WHO/ISUP前列腺分级分组4组，可见神经侵犯，未见脉管内癌栓，
                                 癌组织占该针前列腺穿刺组织40%，免疫组化结果：P504S(+)、P63(-)、34βE12(-)、PSA(+)、PSAP(+)、AR(+)、P53(-)、Ki-67(2%+)。
                                 """)

class PatientHistory(BaseModel):
    """患者详细病史.<br>
    history:历史检查结果 list[{"modality": "CT", "result_str": "检查结果","date":"2025-3-18 16:17:13"}]<br>
    modality：准备进行检查类型<br>
    studypart:准进行的检查部位<br>
    report:近期相同部位检查结果 list [{"date":"2023-3-14","part":"颅脑平扫","modality":"CT","conclusion":"报告结论"}]<br>
    user_id:对话ID string<br>
    chat_name：聊天助手的名字 string<br>
    html:输出html格式 bool <br>
    """
    history:str=Field(title="患者历史检查结果详情", example="""
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
                      """)
    modality: str = Field(title="准备进行检查类型", example="CT")
    studypart:str=Field(title="准进行的检查部位",example="颅脑")
    report:str=Field(title="近期相同部位检查结果",example="""
                    [{"date":"2023-3-14","part":"颅脑平扫","modality":"CT","result":"急诊报告：双侧额顶叶、基底节区、桥脑腔隙性脑梗塞及缺血灶。所见均前相仿。必要时MRI。"},
                    {"date":"2023-3-13","part":"上腹部/肝胆/脾/胰平扫,颅脑平扫,胸部/肺平扫","modality":"CT","result":"急诊报告：1.双侧额顶叶、基底节区、桥脑腔隙性脑梗塞及缺血灶。必要时MRI。2.新见左侧胸腔积液，双肺炎症，以左肺下叶明显。3.左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚。原双肺多个小结节，部分现显示不清。右侧斜裂陈旧灶；肺气肿。右肺散在慢性炎症。左膈膨隆。心包少许积液。左肺门可疑软组织影，肿大淋巴结可能。4.间位结肠；肝右前叶包膜下钙化灶；同前相仿。升结肠憩室。脐部腹壁密度增高。附见左肾上腺粗。"},
                    {"date":"2022-11-10","part":"颅脑平扫,胸部/肺平扫","modality":"CT","result":"急诊报告：1、左肺上叶术后改变，术区周围少许慢性炎症并邻近胸膜增厚；2、右肺上叶后段新见斑块状影，考虑炎症可能，建议治疗后复查除外其他。 3、双肺多个小结节；同前相仿。右侧斜裂陈旧灶；肺气肿。双下肺少许慢性炎症。4、左膈膨隆。5、双侧额顶叶、基底节区少许缺血灶、腔梗，老年脑；请结合临床必要时MRI检查。6、附见：间位结肠；肝右前叶包膜下钙化灶；同前相仿。右侧上颌窦及左侧蝶窦炎症。"},
                    {"date":"2023-8-21","part":"颅脑平扫_1.5T,血管成像","modality":"MR","result":"1.双侧额顶叶、基底节区缺血灶较前稍增多；脑小血管病变，Fazekas 1级；老年脑。2.脑动脉硬化。3.附见：副鼻窦少许炎症。请结合临床。"},
                    {"date":"2021-12-30","part":"颅脑+平扫MRA","modality":"MR","result":"1.双侧额顶叶白质多发缺血灶，老年脑改变，基本相仿。2.颅脑MRA：脑动脉硬化。3.附见：蝶窦炎。"},
                    {"date":"2020-3-14","part":"颅脑平扫+增强_1.5T","modality":"MR","result":"双侧额顶叶白质少许小缺血灶。"}]
                     """)
    user_id: str = Field(title="对话ID", example="xxxx-xxxx-xxx1-xxx1")
    chat_name: str = Field(title="聊天助手", example='小影')
    html:bool=Field(default=False,title="输出HTML格式", example=False)


async def patient_analyze(history:str,modality:str,studypart:str,reports:str,chat_name:str="小影",user_id:str=None):
    # try:
    history_list=json.loads(history)
    reports_list=json.loads(reports)
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
        history_str="\n".join(result)
        ordered_keys=['date',"part","modality","result"]
        result=[]
        for item in reports_list:
            line=','.join(f"{key}:{item[key]}" for key in ordered_keys)
            line=line.replace("modality","类型")
            line=line.replace("result","结果")
            line=line.replace("date","日期")
            line=line.replace("part","检查部位")
            result.append("- "+line)
        reports_str="\n".join(result)
        
        prompt=f""" 
        ## 角色：你是一个经验丰富的主任医师，擅长用简洁的语言指出疾病的核心要点
        ## 任务：请总结以下患者的病史情况，将患者的主要疾病按照系统进行总结，以Markdown格式结构化输出:
                "{history_str}"
                """
        yield '<p style="color: blue; font-weight: bold;">检索中...</p>'
        doctor_llm = ChatOpenAI(
            base_url=XINFERENCE,  # 本地模型API地址
            model=LLM_NAME,            # 模型名称
            temperature=0.1,
            max_tokens=8192,                    # 每次生成的最大token数
            api_key="EMPTY",
            streaming=True                      # 启用流式输出
        )
        his = ""
        for chunk in doctor_llm.stream(prompt):
            response_chunk = chunk.content
            his += response_chunk
            yield response_chunk
            await asyncio.sleep(0)
        yield "\n"
        # print(his)
        prompt=f"""
        ## 背景:有一名患者即将来到放射科进行检查，患者的检查部位："{studypart}"，检查类型："{modality}"
        ## 角色:你是一个经验丰富、工作严谨的放射科主任医师，负责指导年轻医生准确阅片，避免漏诊和误诊。
        ## 任务:请根据患者的信息，提醒初级放射医生阅片时需要注意的要点，以markdown格式结构化输出,包括[特别关注点,扫描技术细节,综合考虑因素]三个部分:
        - 患者病史："{his}"
        - 患者最近的检查结果:"{reports_str}"
        """
        answer = Query_steam(prompt, chat_name, user_id)
        cont = ""
        for ans in answer:
            if ans.content[len(cont):] not in cont:
                # print(ans.content[len(cont):], end='', flush=True)
                yield ans.content[len(cont):]
                await asyncio.sleep(0)
            cont = ans.content   
    else:
        yield "该病人无相关病史"
    # except Exception as e:
    #     yield f"输入错误:{e}"




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
            # print(ans.content[len(cont):], end='', flush=True)
            yield ans.content[len(cont):]
            await asyncio.sleep(0)
        cont = ans.content

    # 第二阶段，生成参考文献列表
    # 保留被大模型选用的引文或者包含图片的引文
    reference_index = re.findall(r"##(\d+)\$\$", ans.content)
    if reference_index:
        reference_index = [int(x) for x in reference_index]
    reference_chunks = []
    for index, ref in enumerate(ans.reference):
        if (index in reference_index) or (len(ref["image_id"]) > 0 and index<2):
            reference_chunks.append(ref)
    # 合并同一文件的多个页码
    merged_docs = {}
    send_references=[]
    for doc in reference_chunks:
        try:
            doc['page'] = list(set([int(x[0]) for x in doc['positions']]))
        except:
            doc['page'] = []
        send_references.append(doc)
        if doc['document_id'] not in merged_docs :
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
    # 返回参考文献列表
    # print(references)
    yield references
    await asyncio.sleep(0)
    # 第三阶段 异步获取引文截图或引文片段
    if re.search("知识库[中]未" ,ans.content) is None:
        asyncio.create_task(send_reference_async(send_references, user_id))
    # 第四阶段，根据回答内容，生成病例检索关键词
    keywords = await asyncio.to_thread(generate_probe, ans.content)
    keywords = keywords.replace(" ", "%20")
    yield f'<a href="{ENDPOINT_IP}/cases?keywords={keywords}" target="_blank" style="font-size:18px; color:darkred;">相关病例图片</a>'


async def send_reference_async(reference_chunks, user_id: str):
    """异步发送参考文献内容"""
    if not reference_chunks:
        return
    doc_content=""
    for chunk in reference_chunks:
        try:
            extension = os.path.splitext(chunk['document_name'])[1][1:]  # 去掉点
            content = None

            # 异步执行阻塞IO操作（如文件解析）
            if extension == "pdf":
                content = await asyncio.to_thread(get_pdf_content, chunk)
            elif extension == "pptx":
                content = await asyncio.to_thread(get_ppt_content, chunk)
            else:
                content = await asyncio.to_thread(get_other_content, chunk)
                if content in doc_content: #避免重复
                    content=None
            if content:
                # 通过WebSocket实时推送
                await manager.send_message(json.dumps({
                    'type': extension,
                    'name': chunk['document_name'],
                    'content': content
                }), user_id)
        except Exception as e:
            logger.error(f"文献发送失败: {str(e)}")




@app.get('/get_uuid')
async def get_uuid():
    """获得一个新的uuid，用来填入rag_ask，以区分不同的对话session

    Returns:
        str: 16位的随机UUID
    """
    return {"uuid":uuid.uuid4()}


@app.post("/login")
async def login(hospitalID: str, hospitalName: str):
    """登录，一个医院使用同一个账户

    Args:
        hospitalID (str): 医院组织机构代码
        hospitalName (str): 医院名称
    """
    global data_name, chat_agent_name
    data_name, chat_agent_name = init_chat_agent(hospitalID, hospitalName)
    if data_name + chat_agent_name == "":
        return "login succeed"
    else:
        return "login faild"


@app.post('/Coincidence')
async def Coincidence(conclusion:Diagnosis):
    """判断放射和病理诊断是否相符<br>
    输入格式<br>
      radology_result:放射诊断<br>
      pathlogy_result:病理诊断<br>
    返回格式：{"reason":"判断理由","result":"符合/基本符合/不符合"}"""
    return Match_result_LLM(conclusion.radology_result, conclusion.pathlogy_result)


@app.post('/rag_ask')
async def rag_ask(query: AskRequest):
    """流式返回放射决策大模型的回答

    Args:
        query.question (str): 用户提出的问题
        query.chat_name(str):聊天助手的名字
        query.user_id(str):通过get_uuid获得的对话ID
    """

    processor=OptimizedProcessor
    rag=await processor.decide_rag_usage(query.question)
    if not rag:   #简单聊天
        return StreamingResponse(simple_chatbot.generate(query.user_id,query.question),
                            media_type='text/plain')
    else:        #使用知识库聊天
        return StreamingResponse(Query(question=query.question, chat_name=query.chat_name, user_id=query.user_id),
                             media_type='text/plain')

@app.post("/patient_summury")
async def patient_summury(query: PatientHistory):
    """总结患者的病史

    Args:<br>
        history（str）:历史检查结果 string<br>
        modality（str）：准备进行检查类型<br>
        studypart（str）:准进行的检查部位<br>
        report（str）:近期相同部位检查结果<br>
        user_id（str）:对话ID string<br>
        chat_name（str）：聊天助手的名字 string<br>
        html(bool):  True输出HTML格式,False输出markdown格式 <br>
    Returns:<br>
        输出为string: html=True为直接输出，False为流式输出
    """
    if not query.html:
        return StreamingResponse(patient_analyze(
                    history=query.history,
                    modality=query.modality,
                    studypart=query.studypart,
                    reports=query.report,
                    chat_name=query.chat_name, 
                    user_id=query.user_id),
                media_type='text/plain')
    else:
        collect_result=patient_analyze(
                            history=query.history,
                            modality=query.modality,
                            studypart=query.studypart,
                            reports=query.report,
                            chat_name=query.chat_name, 
                            user_id=query.user_id)
        result=[]
        async for item in collect_result:
            result.append(item)
            await asyncio.sleep(0)
        result="".join(result)
        result=result.replace("检索中...","")
        result=markdown(result)
        result=f"""<!DOCTYPE html>
            <html lang="zh">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>大模型分析报告</title>
            </head>
            <body>
            {result}
            </body>
            </html>
        """
        return result.replace("\n", "")
    
@app.post('/long_think')
async def long_think(query: AskRequest):
    """长思考模式，返回更详细信息"""
    if query.question[0]=="{":
        return StreamingResponse(patient_analyze(question=query.question, chat_name=query.chat_name, user_id=query.user_id),
                            media_type='text/plain')
    agent = KnowledgeAgent()
    return StreamingResponse(agent.main_chain(question=query.question),
                             media_type='text/plain')

    
@app.get('/list_case')
async def list_case(keywords: str):
    """返回病例库中的相关病例图片

    Args:
        keywords (_type_): 病例关键词，来源于rag_ask返回的最后一行
    """
    if re.search(r'[\u4e00-\u9fff]+',keywords):
        keywords=generate_probe(keywords)
    return search_case(keywords)


@app.get("/list_docs")
async def list_docs(keyword:str=None):
    """列出指定知识库的所有文档

    Args:
        keyword (str): 查询关键词
    """
    if isinstance(keyword,str):
        if keyword.strip()=='':
            keyword=None
    result= Show_all_docs(dataset_name=DEFAUT_DATA,keyword=keyword,doc_id=None)
    return {"files":result}


@app.delete("/del_docs")
async def Del_docs(doc_id):
    """ 删除指定文档

    Args:
        doc_id (list): 文档id
    """
    Delete_documents(DEFAUT_DATA, doc_id)


@app.post("/uploadfiles")
async def upload_folder( files: List[UploadFile]=File(...)):
    """上传知识库文档，并解析，文档大小不得超过2G

    Args:
        files (string): 文件地址列表
    """
    dataset = List_datasets(name=DEFAUT_DATA)
    if not dataset:
        return f"can't find dataset {DEFAUT_DATA}"
    dataset=dataset[0]
    doc_blobs=[]
    for file in files:
        # 获取文件的完整路径（绝对路径）
        file_extension = os.path.splitext(os.path.basename(file.filename))[1]
        if file_extension.lower() not in ['.pdf', '.docx', '.pptx', '.xlsx', '.doc', 'xls', 'ppt',
                                            '.txt', '.jpg', '.jpeg', '.png', '.bmp']:
            continue
        if file.size>1024*1024*MAX_FILE_UPLOAD:
            print("文件过大")
            continue
        # 将合法文件添加到列表中
        # upload_single_file(dataset[0], file)
         # 上传文件列表
        
        content=await file.read()
        content=BytesIO(content)
        doc_blobs.append({
            "displayed_name": file.filename,
            "blob": content
        })
    result=dataset.upload_documents(doc_blobs)
    # 解析所有上传文件
    Parse_documents(DEFAUT_DATA)
    return result
    
@app.post("/uploadCaseFiles")
async def upload_case_folder( files: List[UploadFile]=File(...)):
    """上传病例文件

    Args:
        files (string): 文件地址列表
    """
    dataset = List_datasets(name=DEFAUT_CASE)
    if not dataset:
        return f"can't find dataset {DEFAUT_CASE}"
    dataset=dataset[0]
    doc_blobs=[]
    for file in files:
        # 获取文件的完整路径（绝对路径）
        file_extension = os.path.splitext(os.path.basename(file.filename))[1]
        if file_extension.lower() not in ['.pdf', '.docx', '.pptx', '.xlsx', '.doc', 'xls', 'ppt',
                                            '.txt', '.jpg', '.jpeg', '.png', '.bmp']:
            continue
        if file.size>1024*1024*MAX_FILE_UPLOAD:
            print("文件过大")
            continue
        # 将合法文件添加到列表中
        # upload_single_file(dataset[0], file)
         # 上传文件列表
        
        content=await file.read()
        content=BytesIO(content)
        doc_blobs.append({
            "displayed_name": file.filename,
            "blob": content
        })
    result=dataset.upload_documents(doc_blobs)
    # 解析所有上传文件
    Parse_documents(DEFAUT_CASE)
    return result    


if __name__ == "__main__":
    uvicorn.run(
        app="agent_server:app",
        host="0.0.0.0",
        port=6081,
        workers=1,
        limit_concurrency=1000,
        timeout_keep_alive=300,
        headers=[("Server", "None")],
        proxy_headers=True
    )
