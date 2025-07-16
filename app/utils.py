import io
import os
import json
import re
import base64
import time
from PIL import Image
from io import BytesIO
import requests
import config
from sentence_transformers import util
from app import model

def prompt_format(text):
    result = re.sub(r'\n    \n    ', ' ', text)
    result = re.sub(r'\n    ', '', result)
    result = re.sub(r'\n', ' ', result)
    return result

# 定义 JSON 文件路径
OPERATION_FILE = 'operation_history.jsonl'
STYLE_FILE = 'style_history.jsonl'
ATTITUDE_FILE = 'attitude_history.jsonl'
CANVAS_DIR = os.path.join('screenshot', 'canvas')
BBOX_DIR = os.path.join('screenshot', 'bbox')

def save_screenshot(base64_image_canvas, base64_image_selection, timestamp, workpath):
    canvas_image_data = base64.b64decode(base64_image_canvas)
    canvas_image = Image.open(io.BytesIO(canvas_image_data))
    filename = os.path.join(workpath, CANVAS_DIR, f'{timestamp}.jpg')
    canvas_image.save(filename)
    print(f'Save screenshot to {filename}')
    
    selection_image_data = base64.b64decode(base64_image_selection)
    selection_image = Image.open(io.BytesIO(selection_image_data))
    filename = os.path.join(workpath, BBOX_DIR, f'{timestamp}.jpg')
    selection_image.save(filename)
    print(f'Save screenshot to {filename}')

def save_operation(message, time_stamp, workpath, analysis):
    operation = {
        "message": message,
        "time_stamp": time_stamp,
        "canvas": os.path.join(workpath, CANVAS_DIR, f'{time_stamp}.jpg'),
        "bbox": os.path.join(workpath, BBOX_DIR, f'{time_stamp}.jpg'),
        "analysis": analysis
    }
    with open(os.path.join(workpath, OPERATION_FILE), 'a') as file:
        file.write(json.dumps(operation) + '\n')

def save_style(style, time_stamp, workpath):
    style = {
        "style": style,
        "time_stamp": time_stamp
    }
    with open(os.path.join(workpath, STYLE_FILE), 'a') as file:
        file.write(json.dumps(style) + '\n')

def save_attitude(text, img_url, time_stamp, attitude, explaination, workpath):
    attitude = {
        "text": text,
        "img_url": img_url,
        "time_stamp": time_stamp,
        "attitude": attitude,
        "explaination": explaination
    }
    with open(os.path.join(workpath, ATTITUDE_FILE), 'a') as file:
        file.write(json.dumps(attitude) + '\n')

# 读取 JSON 文件中的历史记录
def read_history():
    if not os.path.exists(OPERATION_FILE):
        with open(OPERATION_FILE, 'w') as file:
            file.write('')
    with open(OPERATION_FILE, 'r') as file:
        return json.load(file)

# 写入更新后的历史记录到 JSON 文件
def write_history(history):
    if not os.path.exists(OPERATION_FILE):
        with open(OPERATION_FILE, 'w') as file:
            file.write('')
    with open(OPERATION_FILE, 'w') as file:
        json.dump(history, file, indent=4)  # indent=4 用于格式化输出
        
def image_to_base64(image_path, type):
    # 打开图片
    with Image.open(image_path) as img:
        # 将图片转换为字节流
        buffered = BytesIO()
        img.save(buffered, format=type)
        # 将字节流编码为Base64
        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return img_base64

def get_operation_data(last_data1, last_data2):
    operation = last_data1['message']
    last_canvas1 = image_to_base64(last_data1['canvas'], "JPEG")
    last_bbox1 = image_to_base64(last_data1['bbox'], "JPEG")
    if last_data2:
        last_canvas2 = image_to_base64(last_data2['canvas'], "JPEG")
        last_bbox2 = image_to_base64(last_data2['bbox'], "JPEG")
        operation_data = [
            {
                "type": "text", 
                "text": f"{operation}，接下来四张图片分别为当前的设计方案、用户修改前的设计方案、当前所关注的部分、用户修改前所关注的部分。"
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_canvas1}"
                }
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_canvas2}"
                }
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_bbox1}"
                }
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_bbox2}"
                }
            }
        ]
    else:
        operation_data = [
            {
                "type": "text", 
                "text": f"{operation}，接下来两张图片分别为当前的设计方案、当前所关注的部分。"
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_canvas1}"
                }
            }, 
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{last_bbox1}"
                }
            }
        ]
    return operation_data

def get_attitude_data(last_data1):
    if last_data1['text'] != "":
        attitude = [{
            "type": "text", 
            "text": f"人类设计师{last_data1['attitude']}了AI生成的内容({last_data1['attitude']})，原因可能是{last_data1['explaination']}"
        }]
    else:
        url = last_data1['img_url']
        # 请求图片数据
        response = requests.get(url)
        if response.status_code == 200:
            # 将图片转换为500x500的缩略图，并存储为Base64编码
            image = Image.open(BytesIO(response.content))
            image.thumbnail((256, 256))
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            attitude = [
                {
                    "type": "text", 
                    "text": f"人类设计师{last_data1['attitude']}了AI生成的图片，如下所示，原因可能是{last_data1['explaination']}"
                }, 
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_str}"
                    }
                }
            ]
    return attitude

def get_msg_num(work_path):
    file_path = os.path.join(work_path, 'messages.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    with open(file_path, 'r') as file:
        data = json.load(file)
    return len(data)

def get_dialog(work_path, prompt, server, current_time):
    file_path = os.path.join(work_path, 'messages.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    with open(file_path, 'r') as file:
        data = json.load(file)

    # 选取出最近30s的聊天记录
    if config.style == 'DISC' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_DISC * 1000
        short_memory_selected_num = config.short_memory_selected_num_response_DISC
        long_memory_selected_num = config.long_memory_selected_num_response_DISC
    elif config.style == 'DISC' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_DISC * 1000
        short_memory_selected_num = config.short_memory_selected_num_proactive_chat_DISC
        long_memory_selected_num = config.long_memory_selected_num_proactive_chat_DISC
    # elif config.style == 'OSTB' and not server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_OSTB * 1000
    #     short_memory_selected_num = config.short_memory_selected_num_response_OSTB
    #     long_memory_selected_num = config.long_memory_selected_num_response_OSTB
    # elif config.style == 'OSTB' and server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_OSTB * 1000
    #     short_memory_selected_num = config.short_memory_selected_num_proactive_chat_OSTB
    #     long_memory_selected_num = config.long_memory_selected_num_proactive_chat_OSTB
    elif config.style == 'SCOL' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_SCOL * 1000
        short_memory_selected_num = config.short_memory_selected_num_response_SCOL
        long_memory_selected_num = config.long_memory_selected_num_response_SCOL
    elif config.style == 'SCOL' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_SCOL * 1000
        short_memory_selected_num = config.short_memory_selected_num_proactive_chat_SCOL
        long_memory_selected_num = config.long_memory_selected_num_proactive_chat_SCOL
    elif config.style == 'INDW' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_INDW * 1000
        short_memory_selected_num = config.short_memory_selected_num_response_INDW
        long_memory_selected_num = config.long_memory_selected_num_response_INDW
    elif config.style == 'INDW' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_INDW * 1000
        short_memory_selected_num = config.short_memory_selected_num_proactive_chat_INDW
        long_memory_selected_num = config.long_memory_selected_num_proactive_chat_INDW
    chat_history = []
    short_memory = []
    long_memory = []
    for msg in data:
        if current_time - msg['time_stamp'] < config.memory_divide * 1000:
            short_memory.append(msg)
            if current_time - msg['time_stamp'] < short_memory_selected_range:
                chat_history.append(msg)
        elif msg['type'] == "text":
            long_memory.append(msg)

    # 如果chat_history为空
    if len(chat_history) == 0:
        attitude_history = get_attitude(work_path, server, current_time)
        if len(attitude_history) == 0:
            # 获取倒数3条
            chat_history = short_memory[-short_memory_selected_num:]
        else:
            return []
    
    long_memory_head = [{
        "type": "text",
        "text": "以下是历史记录中与当前问题相关的对话，请将其作为背景信息。"
    }]
    short_memory_head = [{
        "type": "text",
        "text": "以下是最近的对话记录，请将其作为当前用户的关注重点。"
    }]
    # 计算long_memory中每条记录与prompt的相似度
    if long_memory:
        text_list = [item['text'] for item in long_memory]
        similarity_list = calculate_similarity_batch(text_list, prompt)
        # 按照similarity_list从long_memory中选取相似度最高的三条
        scored_memory = list(zip(similarity_list, long_memory))
        scored_memory.sort(key=lambda x: x[0], reverse=True)
        long_memory_selected = scored_memory[:long_memory_selected_num]
        chat_history = long_memory_head + [item[1] for item in long_memory_selected] + short_memory_head + chat_history
    else:
        chat_history = short_memory_head + chat_history
    chat_history = [{key: value for key, value in item.items() if key != "id" and key != "from" and key != "time_stamp" and key != "similarity"} for item in chat_history]
    for item in chat_history:
        if item.get("type") == "image_url":
            url = item["image_url"].get("url")
            if url:
                # 请求图片数据
                response = requests.get(url)
                if response.status_code == 200:
                    # 将图片转换为256x256的缩略图，并存储为Base64编码
                    image = Image.open(BytesIO(response.content))
                    image.thumbnail((256, 256))
                    buffered = BytesIO()
                    image.save(buffered, format="JPEG")
                    base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    # 替换 url 为 Base64 字符串
                    item["image_url"]["url"] = f"data:image/jpeg;base64,{base64_str}"
    return chat_history

def get_current_dialog(work_path):
    file_path = os.path.join(work_path, 'messages.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    with open(file_path, 'r') as file:
        data = json.load(file)
    chat_history = [{key: value for key, value in item.items() if key != "id" and key != "from" and key != "time_stamp"} for item in data]
    current_chat_history = []
    question = 0
    # 倒序遍历历史记录
    for msg in reversed(chat_history):
        # 如果question_list的个数大于2
        if question == 2:
            break
        if msg['type'] == "text":
            current_chat_history.insert(0, msg)
            match = re.search(r'^(.*?)：', msg['text'])
            if match:
                role = match.group(1)
                if role == '人类提问':
                    question += 1
        elif msg['type'] == "image_url":
            url = msg["image_url"].get("url")
            if url:
                # 请求图片数据
                response = requests.get(url)
                if response.status_code == 200:
                    # 将图片转换为256x256的缩略图，并存储为Base64编码
                    image = Image.open(BytesIO(response.content))
                    image.thumbnail((256, 256))
                    buffered = BytesIO()
                    image.save(buffered, format="JPEG")
                    base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    # 替换 url 为 Base64 字符串
                    msg["image_url"]["url"] = f"data:image/jpeg;base64,{base64_str}"
                    current_chat_history.insert(0, msg)
    return current_chat_history

def get_operation(work_path, server, current_time):
    # 定义文件路径
    file_path = os.path.join(work_path, 'operation_history.jsonl')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            file.write('')
    with open(file_path, "r", encoding="utf-8") as file:
        # 将所有行读取并解析为字典
        data = [json.loads(line) for line in file]
    
    # 筛选出最近30s内的数据
    if config.style == 'DISC' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_DISC * 1000
    elif config.style == 'DISC' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_DISC * 1000
    # elif config.style == 'OSTB' and not server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_OSTB * 1000
    # elif config.style == 'OSTB' and server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_OSTB * 1000
    elif config.style == 'SCOL' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_SCOL * 1000
    elif config.style == 'SCOL' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_SCOL * 1000
    elif config.style == 'INDW' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_INDW * 1000
    elif config.style == 'INDW' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_INDW * 1000
    operation_history = []
    for item in reversed(data):
        if current_time - item['time_stamp'] > short_memory_selected_range:
            break
        operation = {
            "type": "text", 
            "text": item['analysis']
        }
        operation_history.insert(0, operation)

    return operation_history

def get_attitude(work_path, server, current_time):
    # 读取JSONL文件
    file_path = os.path.join(work_path, 'attitude_history.jsonl')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            file.write('')

    with open(file_path, "r", encoding="utf-8") as file:
        # 将所有行读取并解析为字典
        data = [json.loads(line) for line in file]
    
    # 筛选出最近30s内的数据
    if config.style == 'DISC' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_DISC * 1000
    elif config.style == 'DISC' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_DISC * 1000
    # elif config.style == 'OSTB' and not server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_OSTB * 1000
    # elif config.style == 'OSTB' and server:
    #     short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_OSTB * 1000
    elif config.style == 'SCOL' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_SCOL * 1000
    elif config.style == 'SCOL' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_SCOL * 1000
    elif config.style == 'INDW' and not server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_response_INDW * 1000
    elif config.style == 'INDW' and server:
        short_memory_selected_range = config.context_range * config.short_memory_selected_range_proactive_chat_INDW * 1000
    attitude_history = []
    for item in reversed(data):
        if current_time - item['time_stamp'] > short_memory_selected_range:
            break
        attitude_history = get_attitude_data(item) + attitude_history

    return attitude_history

def save_pre_proactive_response(res, id, work_path, socketio):
    behavior = res['behavior']
    timestamp = res['time_stamp']
    file_path = os.path.join(work_path, 'messages.json')
    action_path = os.path.join(work_path, 'action_history.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    if not os.path.exists(action_path):
        with open(action_path, 'w') as file:
            json.dump([], file)
    with open(action_path, 'r') as file:
        data = json.load(file)
    action = {'id': id, 'title': "主动交流", 'action': behavior["context"], 'description': behavior["context"]}
    data.insert(0, action)
    with open(action_path, 'w') as file:
        json.dump(data, file, indent=4)
    socketio.emit('AI_action', action, namespace='/')
    if(behavior["type"] == '1'):
        response = res['text']
        print(f"回复：{response}")
        AI_msg = { "id":id, "type": "text", "text": f"AI主动交流：{response}", "time_stamp": timestamp }
        with open(file_path, 'r') as file:
            data = json.load(file)
        data.append(AI_msg)
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
    else:
        AI_msg_img = { "id":id, "type": "image_url", "image_url": {"url": res["image"]}, "time_stamp": timestamp }
        with open(file_path, 'r') as file:
            data = json.load(file)
        data.append(AI_msg_img)
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)

def calculate_similarity_batch(list, text):
    # 将字符串列表和目标字符串一起编码为向量
    embeddings1 = model.encode(list, clean_up_tokenization_spaces=True, show_progress_bar=False)
    embedding2 = model.encode(text, clean_up_tokenization_spaces=True)

    # 计算每个向量与目标向量的余弦相似度
    similarities = util.cos_sim(embeddings1, embedding2)

    # 将相似度矩阵转换为 Python 列表
    return similarities.squeeze(1).tolist()