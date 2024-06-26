import asyncio
import base64
import re
import shutil
import sys
import os
import json
import time
from fastapi import FastAPI, Form, Request, File, UploadFile, WebSocket
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
import requests
import uvicorn
from pydantic import BaseModel
from typing import Union
from db_manager import DatabaseManager

from utils import Utils


def resource_path(relative_path):
    """获取程序中所需文件资源的绝对路径"""
    try:
        # PyInstaller创建临时文件夹,将路径存储于_MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


app = FastAPI()

config_path = resource_path('gui/config.json')
config = json.loads(open(config_path, 'rb').read())
config_clone = config.copy()  # 备份以便于在写入文件中恢复相对路径
paths_to_convert = [
    'web_path',
    'web_cache_path',
    'index_path',
    'model_path',
    'exists_index_path',
    'metainfo_path',
    'db_path',
    'ui']
config.update({key: resource_path(config[key]) for key in paths_to_convert})
utils = Utils(config)

db = DatabaseManager(config['db_path'])


def delete_old_files(directory):
    """删除创建超过一定时间的缓存文件"""
    # 获取当前时间
    current_time = time.time()
    # 设置阈值为10分钟
    threshold = 600

    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        # 获取文件的创建时间
        creation_time = os.path.getctime(file_path)
        # 计算文件的存在时间
        age = current_time - creation_time
        # 判断是否超过阈值
        if age > threshold:
            # 删除文件
            os.remove(file_path)


async def update_index():
    """更新索引"""
    utils.remove_nonexists()
    need_indexs = []
    for image_dir in config['search_dir']:
        need_index = utils.index_target_dir(image_dir)
        need_indexs.extend(need_index)
    nc = len(need_indexs)
    if nc == 0:
        await connection_manager.send_message('100')
    for i, (idx, fpath) in enumerate(need_indexs):
        utils.update_ir_index(idx, fpath)
        progress = int((i + 1) / nc * 100)
        await connection_manager.send_message(str(progress))
        await asyncio.sleep(0) # 插入一个小延迟，使得websocket能够正常发送消息
    utils.exists_index = utils.get_exists_index()


class ConnectionManager:
    """管理WebSocket连接"""

    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


connection_manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    html_file = open(config['web_path'], 'r', encoding='utf-8').read()
    if not os.path.exists(config['web_cache_path']):
        # 检测缓存目录是否存在，不存在则创建
        os.makedirs(config['web_cache_path'])
    # 删除超过24小时的文件
    delete_old_files(config['web_cache_path'])
    return html_file


@app.post("/uploadfile/")
async def create_upload_file(
        file: UploadFile = File(None),
        url: str = Form(None)):
    """上传文件或下载网址文件"""
    filename = ""
    if file is not None:
        # 如果是文件上传
        filename = f"image_{int(round(time.time() * 1000))}." + \
            file.filename.split(".")[-1]
        with open(f"{config['web_cache_path']}/{filename}", "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    elif url is not None:
        # 如果是网址下载文件
        filename = f"image_{int(round(time.time() * 1000))}." + \
            url.split("/")[-1].split(".")[-1]  # 从网址中提取文件名
        response = requests.get(url, stream=True)
        with open(f"{config['web_cache_path']}/{filename}", "wb") as f:
            shutil.copyfileobj(response.raw, f)
    else:
        return {"message": "No file or url provided"}

    nc = 20
    exists_index = utils.get_exists_index()  # 加载索引
    nc = nc if nc <= len(exists_index) else len(exists_index)
    results = utils.checkout(
        f"{config['web_cache_path']}/{filename}",
        exists_index,
        nc)
    results = sorted(results, key=lambda x: x[0], reverse=True)
    results_dict = []
    for i in results:
        similarity = f'{i[0]:.2f} %'
        path = i[1].replace('\\', '/')
        name = path.split('/')[-1].split('.')[0]
        results_dict.append({
            "similarity": similarity,
            "path": path,
            "name": name
        })
    # results_dict = sorted(results_dict, key=lambda x: x['similarity'], reverse=True)

    return {
        "original_file": {
            "name": filename,
            "path": f"{config['web_cache_path']}/{filename}".encode('utf-8')},
        "results": results_dict}


@app.get("/image/")
async def get_image(image_path: str):
    """获取图片"""
    return FileResponse(image_path)


class RecordForm(BaseModel):
    record: str  # 车牌名
    name: str
    image_path: str
    mangneUrl: Union[str, None] = None
    webUrl: Union[str, None] = None
    note: Union[str, None] = None
    resource_id: Union[int, None] = None  # 数据库resource表的ID
    path_id: Union[int, None] = None  # 数据库path表的ID


@app.post("/addRecord/")
async def addRecord(rf: RecordForm):
    """添加记录"""
    if not os.path.exists(config["record_path"]):
        os.makedirs(config["record_path"])
    if config["record_path"] not in config["search_dir"]:
        config["search_dir"].append(config["record_path"])
        config.update({key: config_clone[key] for key in paths_to_convert})
        with open(config_path, 'wb') as wp:
            wp.write(
                json.dumps(
                    config,
                    indent=2,
                    ensure_ascii=False).encode('UTF-8'))
    if rf.resource_id is not None and rf.path_id is not None:
        # 只有更新时才需要更新resource和path表
        db.update_data(
            'resource', f'title="{rf.record}",mangnetUrl="{rf.mangneUrl}",webUrl="{rf.webUrl}",note="{rf.note}"', f'id={rf.resource_id}')
        path_res = db.query_data('path', f'id={rf.path_id}')
        old_path = path_res[0][2]
        new_path = os.path.join(os.path.dirname(
            old_path), rf.record + os.path.splitext(old_path)[1])
        db.update_data(
            'path', f'title="{rf.record}",path="{new_path}"', f'id={rf.path_id}')
        os.rename(old_path, new_path)
        with open(config["exists_index_path"], 'r', encoding='utf-8') as f:
            index_list = json.loads(f.read())
        index_list = list(map(lambda file: file.replace(old_path, new_path), index_list))
        with open(config["exists_index_path"], 'wb') as f:
            f.write(json.dumps(index_list, indent=2,
                     ensure_ascii=False).encode('UTF-8'))
        await update_index()
        return {"code": 200, "message": "Record updated successfully", "id": {"resource_id": rf.resource_id, "path_id": rf.path_id}}
    # 将不允许的字符替换为中文字符
    replacements = {
        '<': '《',
        '>': '》',
        ':': '：',
        '"': '“',
        '/': '_',
        '\\': '_',
        '|': '｜',
        '?': '？',
        '*': '＊'
    }
    cleaned_record = re.sub(r'[<>:"/\\|?*]',
                            lambda m: replacements[m.group()],
                            rf.record.strip())  # 去除非法字符
    # 获取文件名和文件后缀
    base_name, ext = os.path.splitext(os.path.basename(rf.name))
    new_filename = f'{cleaned_record}{ext}'
    new_path = os.path.join(config["record_path"], new_filename)
    # 如果文件已存在，则在文件名后添加标识符
    index = 1
    while os.path.exists(new_path):
        new_filename = f"{cleaned_record}（{index}）{ext}"
        new_path = os.path.join(config["record_path"], new_filename)
        index += 1
    shutil.move(rf.image_path, new_path)

    await update_index()

    if rf.resource_id is None and rf.path_id is None:
        resource_id, path_id = db.insert_data(
            (rf.record, rf.mangneUrl, rf.webUrl, rf.note, new_path))  # 插入数据
    elif rf.resource_id is not None and rf.path_id is None:
        resource_id, path_id = db.insert_data(
            (rf.record, new_path, rf.resource_id),False
        )

    return {"code": 200, "message": "Record added successfully", "id": {"resource_id": resource_id, "path_id": path_id}}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await connection_manager.send_message(data)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)


@app.get("/updateIndex/")
async def updateIndex():
    """更新索引"""
    await update_index()
    return {"code": 200, "message": "Index updated successfully"}

@app.get("/getRecordInfo/")
async def getRecordInfo(record: str):
    """获取记录信息"""
    return db.query_data('resource', f'title="{record}"')


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5555)
