# app/routes.py
from anyio import current_time
from app import app
from flask import request, jsonify, send_from_directory
import asyncio
from . import utils
from . import prompts
from . import gpt
from app import socketio
import os
import json
import time
import re
import config
import threading
from concurrent.futures import Future
import shutil
import random

count = 0
last_active_time = None
pre_proactive_response = None
inactive_change = False
inactive_update = False
history_scale = 0.3
DISC_follow_up = False # indicate whether a follow-up chat should be sent
user_last_style = 'DISC'

# 获取 routes.py 文件所在目录的上一级目录
current_directory = os.path.dirname(os.path.abspath(__file__))
parent_directory = os.path.dirname(current_directory)

# 定义 user_data 目录路径
user_data_directory = os.path.join(parent_directory, "user_data")
f_path = os.path.join(user_data_directory, 'workpath.json')
if os.path.exists(f_path):
    with open(f_path, 'r') as file:
        work_path = json.load(file)
else:
    work_path = ""
    
mode_path = os.path.join(work_path, 'mode.json')
if os.path.exists(mode_path):
    with open(f_path, 'r') as file:
        config.style = json.load(file)
else:
    config.style = "DISC"
    
max_msg_id = 0
    
background_task_thread1 = None
background_task_thread2 = None
coupling_style_judgement_thread3 = None

# 全局事件对象，用于停止后台任务
stop_event_task1 = threading.Event()
stop_event_task2 = threading.Event()
# 后台不断判断各种cue
stop_coupling_style_judgement = threading.Event()

style_change_lock = threading.Lock()

@app.route('/')
def home():
    return "Hello, Flask!"

@app.route('/images/<filename>')
def serve_image(filename):
    images_dir = os.path.join(work_path, 'images')
    return send_from_directory(images_dir, filename)

@app.route('/save_operation', methods = ['POST'])
def save_operation():
    payload = request.get_json()
    message = payload.get('message', '')
    time_stamp = payload.get('timeStamp', '')
    canvas_screenshot = payload.get('canvasScreenshot', '')
    selection_screenshot = payload.get('selectionScreenshot', '')
    print(f'saving operation: {message}')
    utils.save_screenshot(canvas_screenshot, selection_screenshot, time_stamp, work_path)
    res = asyncio.run(gpt.get_operation_analysis(work_path, message, time_stamp))
    utils.save_operation(message, time_stamp, work_path, res)
    return f"success to save the user operation: {message}"

@app.route('/save_attitude', methods=['POST'])
def save_attitude():
    payload = request.get_json()
    text = payload.get('text', '')
    img_url = payload.get('img_url', '')
    time_stamp = payload.get('timeStamp', '')
    attitude = '接受' if payload.get('attitude', '') else '拒绝'
    action = '主动生成对话' if text else '主动生成图片'
    content = text if text else img_url
    prompt = prompts.prompt_for_attitude_analysis.format(task=config.task_content, action=action, content=content, attitude=attitude)
    res = asyncio.run(gpt.get_attitude_analysis(work_path, prompt))
    utils.save_attitude(text, img_url, time_stamp, attitude, res.get('text', ''), work_path)
    return f'success to save the attitude to {action}: {content}'

@app.route('/update_range', methods=['POST'])
def update_range():
    data = request.get_json()
    scale = data.get('scale', 1)  # 获取前端传来的比例系数
    history_scale = scale

    # 读取历史记录
    utils.init_json_file()
    history = utils.read_history()

    total_records = len(history)  # 历史记录的总条数
    num_records = max(1, int(total_records * history_scale))  # 根据比例系数计算最近记录的数量

    # 返回最近的 num_records 条记录
    recent_history = history[0:num_records]

    return jsonify(recent_history)

@app.route('/get_data', methods=['GET'])
def get_data():
    print("get_data")
    # 读取历史记录
    utils.init_json_file()
    history = utils.read_history()

    total_records = len(history)  # 历史记录的总条数
    num_records = max(1, int(total_records * history_scale))  # 根据比例系数计算最近记录的数量

    # 返回最近的 num_records 条记录
    recent_history = history[0:num_records]

    text_list = ""
    for item in recent_history:
        text_list += f"\"{item}\""
    msg=[
        {
        "role": "user",
        "content": [
            {"type": "text", "text": utils.prompt_format(prompts.prompt_for_generating.format(task=config.task_content, history = text_list))},
            # {
            # "type": "image_url",
            # "image_url": {
            #     "url": f"data:image/jpeg;base64,{base64_image}",
            # },
            # },
        ],
        }
    ]

    res = asyncio.run(gpt.gpt_temp(msg))
    print(res)

    return jsonify(res)  # 返回所有历史记录

@app.route('/recount', methods=['GET'])
def recount():
    global count
    count = 0
    return jsonify({"message": "count reset"}), 200

@app.route('/chat', methods=['POST'])
def chat():
    global last_active_time, pre_proactive_response, count, DISC_follow_up
    pre_proactive_response = None
    DISC_follow_up = False
    data = request.get_json()
    prompt = data.get('prompt', '')
    id = data.get('id')
    time_stamp = data.get('timeStamp', '')
    res = asyncio.run(gpt.chat(work_path, id, prompt, time_stamp, socketio, False))
    res['id'] = id
    if config.style == 'DISC':
        last_active_time = time.time()
        future = Future()
        pre_proactive_response = future
        threading.Thread(target=lambda: asyncio.run(gpt.pre_chat(work_path, prompt, future))).start()
        count += 1
    return jsonify(res), 200

@app.route('/login', methods=['POST'])
def create_directory():
    global work_path, max_msg_id
    data = request.get_json()
    user_name = data.get("username")
    config.task_content = data.get("task")

    if not user_name:
        return jsonify({"error": "File name is missing"}), 400

    # 检查 user_data 目录是否存在，不存在则创建
    if not os.path.exists(user_data_directory):
        os.makedirs(user_data_directory, exist_ok=True)

    # 定义草稿名称的子目录路径
    user_path = os.path.join(user_data_directory, user_name)
    work_path = user_path
    # 创建草稿名称的子目录
    try:
        os.makedirs(user_path, exist_ok=True)
        os.makedirs(os.path.join(user_path, 'images'), exist_ok=True)
        file_path = os.path.join(user_path, 'messages.json')
        if not os.path.exists(file_path):
            with open(file_path, 'w') as file:
                json.dump([], file)
        os.makedirs(os.path.join(user_path, 'screenshot', 'canvas'), exist_ok=True)
        os.makedirs(os.path.join(user_path, 'screenshot', 'bbox'), exist_ok=True)
        print(user_path)
        file_path = os.path.join(user_data_directory, 'workpath.json')
        with open(file_path, 'w') as file:
            json.dump(work_path, file)
        max_msg_id = utils.get_msg_num(work_path)
        
        # initial style
        config.style = 'DISC'
        # initial interval
        config.trigger_proactive_DISC_interval = 15
        config.trigger_proactive_SCOL_interval = 30
        config.trigger_proactive_INDW_interval = 45

        timestamp = int(time.time() * 1000)
        utils.save_style(config.style, timestamp, work_path)
        init_style_vars()
        return jsonify({"message": f"Directory '{user_path}' created successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/getMessages', methods=['GET'])
def getMessages():
    file_path = os.path.join(work_path, 'messages.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    with open(file_path, 'r') as file:
        data = json.load(file)
    msg_list = []
    for msg in data:
        if msg['type'] == "text":
            match = re.search(r'^(.*?)：', msg['text'])
            if match:
                role = match.group(1)
            match = re.search(r'：(.+)', msg['text'], re.DOTALL)
            if match:
                text = match.group(1)
            if role == 'AI生成回复':
                return_msg = {"id": msg['id'], "text": text, "img_url": "", "sender": "received"}
            elif role == 'AI主动交流':
                return_msg = {"id": msg['id'], "text": text, "img_url": "", "sender": "server"}
            elif role == "AI主动交流&编辑画布":
                return_msg = {"id": msg['id'], "text": text, "img_url": "", "sender": "server"}
            else:
                return_msg = {"id": msg['id'], "text": text, "img_url": "", "sender": "sent"}
            msg_list.append(return_msg)
        else:
            sender = ""
            if msg['from'] == 'passive':
                sender = "received"
            else:
                sender = "server"
            return_msg = {"id": msg['id'], "text": "", "img_url": msg['image_url']['url'], "sender": sender}
            msg_list.append(return_msg)
    return jsonify(msg_list), 200

@app.route('/getActions', methods=['GET'])
def getActions():
    file_path = os.path.join(work_path, 'action_history.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    with open(file_path, 'r') as file:
        data = json.load(file)
    return jsonify(data), 200

@app.route('/getMsgId', methods=['GET'])
def getMsgId():
    global max_msg_id
    id = max_msg_id
    max_msg_id = max_msg_id + 1
    return {"id": id}

@app.route('/style_change', methods=['POST'])
def styleChange():
    if not style_change_lock.acquire(blocking=False):
        print("style_change 正在执行中，跳过此次请求")
        return jsonify({"message": "存在未完成的Style change请求"}), 429
    
    try:
        handle_stop_background_task()
        data = request.get_json()
        config.style = data.get('style', '')
        print(f"Style change to: {config.style}")
        file_path = os.path.join(work_path, 'mode.json')
        with open(file_path, 'w') as file:
            json.dump(config.style, file)
        utils.save_style(config.style, int(time.time() * 1000), work_path)
        init_style_vars()
        handle_start_background_task()
        if config.style == 'DISC':
            proactive_interval = config.trigger_proactive_DISC_interval
        elif config.style == 'SCOL':
            proactive_interval = config.trigger_proactive_SCOL_interval
        else:
            proactive_interval = config.trigger_proactive_INDW_interval
        print(f"proactive_interval: {proactive_interval}")
        return jsonify({
            "message": f"Style change to: {config.style}",
            "proactive_interval": proactive_interval
        }), 200
    finally:
        style_change_lock.release()

# （弃用）15秒内无操作，主动交流
@app.route('/inactive_change', methods=['GET'])
def inactiveChange():
    global inactive_change
    if config.style == 'OSTB':
        inactive_change = True
    return jsonify({"message": "inactive change"}), 200

# （弃用）15秒内无打字，主动交流
@app.route('/inactive_update', methods=['GET'])
def inactiveUpdate():
    global inactive_update
    if config.style == 'OSTB':
        inactive_update = True
    return jsonify({"message": "inactive update"}), 200

@socketio.on('connect')
def handle_connect():
    print(f"Client connected")
    
@app.route('/addContent', methods=['POST'])
def add_content():
    print('addContent')
    msg = request.get_json()
    print(msg)
    action_id = msg.get("action_id")
    node_id = msg.get("node_id")
    action_path = os.path.join(work_path, 'action_history.json')
    if not os.path.exists(action_path):
        with open(action_path, 'w') as file:
            json.dump([], file)
    with open(action_path, 'r') as file:
        data = json.load(file)
    for item in data:
        if item['id'] == action_id and item['node_id'] == "":
            item['node_id'] = node_id
    with open(action_path, 'w') as file:
        json.dump(data, file, indent=4)
    socketio.emit('update_action', msg, namespace='/')
    return jsonify({"message": "update_action"}), 200
    
@socketio.on('refresh')
def refresh():
    try:
        # 清空用户目录下的所有内容
        for item in os.listdir(work_path):
            item_path = os.path.join(work_path, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)  # 删除文件或符号链接
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)  # 删除目录
        default_path = os.path.join(user_data_directory, 'default')
        # 复制 default 目录中的内容到用户目录
        for item in os.listdir(default_path):
            source_item = os.path.join(default_path, item)
            target_item = os.path.join(work_path, item)
            if os.path.isdir(source_item):
                shutil.copytree(source_item, target_item)  # 复制目录
            else:
                shutil.copy2(source_item, target_item)  # 复制文件
        os.makedirs(os.path.join(work_path, 'images'), exist_ok=True)
        os.makedirs(os.path.join(work_path, 'screenshot', 'canvas'), exist_ok=True)
        os.makedirs(os.path.join(work_path, 'screenshot', 'bbox'), exist_ok=True)
        with open(os.path.join(work_path, 'messages.json'), 'r') as file:
            data = json.load(file)
        # 倒序添加time_stamp, 每个对话之间间隔1秒
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        for msg in reversed(data):
            msg['time_stamp'] = timestamp
            timestamp -= 1000
        with open(os.path.join(work_path, 'messages.json'), 'w') as file:
            json.dump(data, file, indent=4)
        utils.save_style(config.style, timestamp, work_path)
        socketio.emit('reload')
        return {"success": True, "message": f"Refreshed."}

    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}

def proactive_conclude():
    global count, max_msg_id
    while not stop_event_task1.is_set():
        if config.style == 'DISC':
            while count < 2 and not stop_event_task1.is_set():
                time.sleep(1)
            if stop_event_task1.is_set():
                print("proactive_conclude stopped.")
                return
            socketio.emit('edit_canvas')
            conclude = asyncio.run(gpt.conclude(work_path, socketio))
            if stop_event_task1.is_set():
                print("proactive_conclude stopped.")
                return
            socketio.emit('AI_conclude', {'id': conclude['action_id'], 'text': conclude['text'], 'img_url': ''})
            count = 0
    print("proactive_conclude stopped.")

def proactive_chat():
    global last_active_time, pre_proactive_response,inactive_change, inactive_update, DISC_follow_up
    while not stop_event_task2.is_set():
        global max_msg_id
        id = max_msg_id
        max_msg_id = max_msg_id + 1

        if config.style == 'DISC' and last_active_time:
            while not stop_event_task2.is_set() and time.time() - last_active_time < (config.trigger_proactive_DISC_interval + random.uniform(0, 5)):
                time.sleep(1)
                print(f"sleeping {time.time() - last_active_time}")
            if not DISC_follow_up:
                if pre_proactive_response:
                    print("proactive response is prepared")
                    if stop_event_task2.is_set():
                        print("proactive_chat stopped.")
                        return
                    res = pre_proactive_response.result()
                    if stop_event_task2.is_set():
                        print("proactive_chat stopped.")
                        return
                    utils.save_pre_proactive_response(res, id, work_path, socketio)
                    socketio.emit('AI_message', {'id': id, 'text': res['text'], 'img_url': res['image']})
                    last_active_time = None
                    last_active_time = time.time()
                    # pre_proactive_response = None
                    DISC_follow_up = True
            else:
                if stop_event_task2.is_set():
                    print("proactive_chat stopped.")
                    return
                time_stamp = int(time.time() * 1000)
                res = asyncio.run(gpt.chat(work_path, id, '', time_stamp, socketio, True))
                if stop_event_task2.is_set():
                    print("proactive_chat stopped.")
                    return
                socketio.emit('AI_message', {'id': id, 'text': res['text'], 'img_url': res['image']})
                last_active_time = time.time()
        elif config.style == 'SCOL':
            while not stop_event_task2.is_set() and time.time() - last_active_time < config.trigger_proactive_SCOL_interval:
                time.sleep(1)
                print(f"sleeping {time.time() - last_active_time}")
            if stop_event_task2.is_set():
                print("proactive_chat stopped.")
                return
            time_stamp = int(time.time() * 1000)
            res = asyncio.run(gpt.chat(work_path, id, '', time_stamp, socketio, True))
            if stop_event_task2.is_set():
                print("proactive_chat stopped.")
                return
            socketio.emit('AI_message', {'id': id, 'text': res['text'], 'img_url': res['image']})
            last_active_time = time.time()
        elif config.style == 'INDW':
            while not stop_event_task2.is_set() and time.time() - last_active_time < config.trigger_proactive_INDW_interval:
                time.sleep(1)
                print(f"sleeping {time.time() - last_active_time}")
            if stop_event_task2.is_set():
                print("proactive_chat stopped.")
                return
            time_stamp = int(time.time() * 1000)
            res = asyncio.run(gpt.chat(work_path, id, '', time_stamp, socketio, True))
            if stop_event_task2.is_set():
                print("proactive_chat stopped.")
                return
            socketio.emit('AI_message', {'id': id, 'text': res['text'], 'img_url': res['image']})
            last_active_time = time.time()
    print("proactive_chat stopped.")

def coupling_style_judgement():
    global user_last_style
    print(f"启动 coupling_style_judgement 线程，ID = {threading.get_ident()}")
    while not stop_coupling_style_judgement.is_set():
        # style_options = ['DISC', 'OSTB', 'SCOL', 'INDW']
        if stop_coupling_style_judgement.is_set():
            print("style judgement is stopped")
            return
        style_options = ['DISC', 'SCOL', 'INDW']

        interrupted = stop_coupling_style_judgement.wait(timeout=10)
        if interrupted:
            print("style judgement is stopped (interrupted during wait)")
            break  # 跳出 while，线程结束
        
        next_AI_style = random.choice(style_options)
        while next_AI_style == user_last_style:
            next_AI_style = random.choice(style_options)
        user_last_style = next_AI_style
        print(f'用户当前的coupling style是：{next_AI_style}')
        
        socketio.emit('change_AI_style', next_AI_style)
    
        
# 启动后台任务事件
@socketio.on('start_background_task')
def handle_start_background_task():
    global background_task_thread1, background_task_thread2, stop_event_task1, stop_event_task2, coupling_style_judgement_thread3, stop_coupling_style_judgement

    # 如果任务1未启动或已停止，则启动
    if background_task_thread1 is None or not background_task_thread1.is_alive():
        stop_event_task1.clear()  # 确保停止事件被清除
        background_task_thread1 = socketio.start_background_task(proactive_conclude)
        print("start background task1")

    # 如果任务2未启动或已停止，则启动
    if background_task_thread2 is None or not background_task_thread2.is_alive():
        stop_event_task2.clear()  # 确保停止事件被清除
        background_task_thread2 = socketio.start_background_task(proactive_chat)
        print("start background task2")
        
    if coupling_style_judgement_thread3 is None or not coupling_style_judgement_thread3.is_alive():
        stop_coupling_style_judgement.clear()
        coupling_style_judgement_thread3 = socketio.start_background_task(coupling_style_judgement)
        print("start transitioning cue judgement")

# 停止后台任务事件
@socketio.on('stop_background_task')
def handle_stop_background_task():
    global background_task_thread1, background_task_thread2, stop_event_task1, stop_event_task2, coupling_style_judgement_thread3, stop_coupling_style_judgement

    # 停止任务1
    if background_task_thread1 and background_task_thread1.is_alive():
        stop_event_task1.set()  
        background_task_thread1.join()  
        background_task_thread1 = None
        print("stop background task1")

    # 停止任务2
    if background_task_thread2 and background_task_thread2.is_alive():
        stop_event_task2.set()  # 通知任务2停止
        background_task_thread2.join()  # 等待任务2停止
        background_task_thread2 = None
        print("stop background task2")

    # stop style judgement
    if coupling_style_judgement_thread3 and coupling_style_judgement_thread3.is_alive():
        stop_coupling_style_judgement.set()  # 通知任务2停止
        coupling_style_judgement_thread3.join()  # 等待任务2停止
        coupling_style_judgement_thread3 = None
        print("stop transitioning cue judgement")

def init_style_vars():
    global count, last_active_time, pre_proactive_response, inactive_change, inactive_update, DISC_follow_up
    count = 0
    last_active_time = time.time()
    pre_proactive_response = None
    inactive_change = False
    inactive_update = False
