import asyncio
from tracemalloc import start
import openai
from sympy import content
import config
import requests
import os
import json
from . import prompts, utils
import re
import base64
from flask_socketio import emit
import time

async def gpt_temp(msg, json_format=False):
    # print(msg)
    try:
        client = openai.AsyncOpenAI(
            api_key=config.OPENAI_KEY,
            base_url=config.OPENAI_BASE_URL
        )
        if json_format:
            response = await client.chat.completions.create(
                model="gpt-4o",
                response_format={ "type": "json_object" },
                messages=msg,
                max_tokens=4096,
            )
        else:
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=msg,
                max_tokens=4096,
            )
        # print(f"response: {response}")
        first_choice = response.choices[0]
        message = first_choice.message
        response_content = message.content
        print(f"生成：{response_content}")
        return response_content
    except Exception as e:
        print(f"Error: GPT生成失败，{str(e)}")
        return json.dumps({
            "text": "出错了，请重试！",
            "image": ""
        })

async def gpt_temp_multi(msgs, json_format=False):
    responses = await asyncio.gather(*(gpt_temp(msg) for msg in msgs))
    return responses

async def text2Image(work_path, prompt):
    # return {
    #             "text": "图片生成成功！",
    #             "image": "https://zos.alipayobjects.com/rmsportal/jkjgkEfvpUPVyRjUImniVslZfWPnJuuZ.png"
    #         }
    try:
        client = openai.AsyncOpenAI(
            api_key=config.OPENAI_KEY,
            base_url=config.OPENAI_BASE_URL
        )
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="512x512",
            quality="standard",
            n=1,
        )
        r = response.data[0].url
        # 使用requests下载图片内容
        print(r)
        response = requests.get(r)

        # 确保请求成功
        if response.status_code == 200:
            # 构建从当前目录到 images 目录的相对路径
            images_dir = os.path.join(work_path, 'images')
            
            # 计算目录中现有的文件数
            file_count = len([name for name in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, name))])

            # 生成新的文件名（例如：'img3.jpg'）
            new_file_name = f'img{file_count}.jpg'
            save_path = os.path.join(images_dir, new_file_name)
            url = f"http://127.0.0.1:5010/images/{new_file_name}"

            # 写入图片数据到文件
            with open(save_path, 'wb') as file:
                file.write(response.content)

            print(f"Image saved to {save_path}")
            return {
                "text": "",
                "image": url
            }
        else:
            print("Failed to download the image")
            return {
                "text": "图片生成失败！",
                "image": ""
            }
    except Exception as e:
        print(f"Error: 调用GPT文生图失败，{str(e)}")
        return {
            "text": "图片生成失败！",
            "image": ""
        }

async def conclude(work_path, socketio):
    title = "编辑画布"
    
    action_path = os.path.join(work_path, 'action_history.json')
    if not os.path.exists(action_path):
        with open(action_path, 'w') as file:
            json.dump([], file)
    with open(action_path, 'r') as file:
        data = json.load(file)
    id = len(data)
    action = {'id': id,'msg_id': None, 'node_id': '', 'title': title, 'action': "判断当前对话中是否包含有效信息，如包含，请将对话内容整理为要点", 'description': "整理近两轮对话观点，总结讨论中有用信息"}
    data.insert(0, action)
    with open(action_path, 'w') as file:
        json.dump(data, file, indent=4)
    
    socketio.emit('AI_action', action, namespace='/')
    
    dialog = utils.get_current_dialog(work_path)
    system_msg = [{'type': 'text', 'text': utils.prompt_format(prompts.system_DISC_conclude.format(task=config.task_content))}]
    msg = [
        {
            "role": "system",
            "content": system_msg
        },
        {
            "role": "user",
            "content": dialog
        }]
    response = await gpt_temp(msg)
    socketio.emit('AI_action_finish', {'id': id, 'success': True}, namespace='/')
    print(f"回复：{response}")
    return {"action_id": id, "text": response, "image":""}

async def chat(work_path, id, prompt, time_stamp, socketio, server):
    start_time = time.time() # start counting
    file_path = os.path.join(work_path, 'messages.json')
    if not os.path.exists(file_path):
        with open(file_path, 'w') as file:
            json.dump([], file)
    
    if server == False:
        print(f"来自用户的提问：{prompt}")
        user_msg = { "id": id-1, "type": "text", "text": f"人类提问：{prompt}", "time_stamp": time_stamp }
        
        if not os.path.exists(file_path):
            with open(file_path, 'w') as file:
                json.dump([], file)
        with open(file_path, 'r') as file:
            data = json.load(file)
        data.append(user_msg)
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
    
    behavior=None
    while not behavior:
        behavior = await behavior_decision(work_path, prompt, server, time_stamp)
    
    if server == True and (config.style == 'SCOL' or config.style == 'INDW'):
        title = "主动交流&编辑画布"
    elif server == True:
        title = "主动交流"
    else:
        title = "生成回复"
        
    action_path = os.path.join(work_path, 'action_history.json')
    if not os.path.exists(action_path):
        with open(action_path, 'w') as file:
            json.dump([], file)
    with open(action_path, 'r') as file:
        data = json.load(file)
    action_id = len(data)
    action = {'id': action_id,'msg_id': id, 'node_id':'', 'title': title, 'action': f"生成“{prompt}”的回复", 'description': behavior["context"]}
    data.insert(0, action)
    with open(action_path, 'w') as file:
        json.dump(data, file, indent=4)
    socketio.emit('AI_action', action, namespace='/')
    
    if(behavior["type"] == '2'):
        if server == False:
            new_prompt = prompts.image_generation_reactive.format(task=config.task_content, user_question=prompt, context=behavior["context"])
        else:
            new_prompt = prompts.image_generation_proactive.format(task=config.task_content, context=behavior["context"])
        
        result = await text2Image(work_path, new_prompt)
        # AI_msg_txt = { "id": id, "type": "text", "text": f"AI{title}：图片已生成！" }
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        if server == False:
            AI_msg_img = { "id": id, "type": "image_url", "image_url": {"url": result["image"]}, "from": "passive", "time_stamp": timestamp}
        else:
            AI_msg_img = { "id": id, "type": "image_url", "image_url": {"url": result["image"]}, "from": "proactive", "time_stamp": timestamp}
        with open(file_path, 'r') as file:
            data = json.load(file)
        # data.append(AI_msg_txt)
        data.append(AI_msg_img)
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
        
        socketio.emit('AI_action_finish', {'id': action_id, 'success': True}, namespace='/')
        return result
    else:
        dialog_history = utils.get_dialog(work_path, prompt, server, time_stamp)
        dialog_history_str = ""
        for item in dialog_history:
            if item.get("type") == "text":
                dialog_history_str += item.get("text") + "\n\n"
        
        operation_history = utils.get_operation(work_path, server, time_stamp)
        operation_history_str = ""
        for item in operation_history:
            operation_history_str += item.get("text") + "\n\n"
        
        attitude_history = utils.get_attitude(work_path, server, time_stamp)
        attitude_history_str = ""
        for item in attitude_history:
            attitude_history_str += item.get("text") + "\n\n"

        # organize system prompt
        if config.style == 'DISC' and server == False:
            system_prompt = prompts.system_DISC_generation_reactive.format(task=config.task_content)
        elif config.style == 'DISC' and server == True:
            system_prompt = prompts.system_DISC_generation_proactive.format(task=config.task_content)
        elif config.style == 'SCOL' and server == False:
            system_prompt = prompts.system_SCOL_generation_reactive.format(task=config.task_content)
        elif config.style == 'SCOL' and server == True:
            system_prompt = prompts.system_SCOL_generation_proactive.format(task=config.task_content)
        elif config.style == 'INDW' and server == False:
            system_prompt = prompts.system_INDW_generation_reactive.format(task=config.task_content)
        elif config.style == 'INDW' and server == True:
            system_prompt = prompts.system_INDW_generation_proactive.format(task=config.task_content)
        
        # organize user prompt
        if server == False:
            user_prompt = prompts.user_generation_reactive.format(user_question=prompt, context=behavior["context"], dialog_history=dialog_history_str, operation_history=operation_history_str, attitude_history=attitude_history_str)
        else:
            user_prompt = prompts.user_generation_proactive.format(context=behavior["context"], dialog_history=dialog_history_str, operation_history=operation_history_str, attitude_history=attitude_history_str)
        
        msg = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
        response = await gpt_temp(msg)
        
        end_time = time.time()
        print(f"本次简化后的chat耗时：{end_time - start_time:.2f}秒")

        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        AI_msg = { "id": id, "type": "text", "text": f"AI{title}：{response}", "time_stamp": timestamp }
        with open(file_path, 'r') as file:
            data = json.load(file)
        data.append(AI_msg)
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)
        
        socketio.emit('AI_action_finish', {'id': action_id, 'success': True}, namespace='/')
        
        return {"text": response, "image":""}

async def pre_chat(work_path, prompt, future):
    try:
        behavior = None
        while not behavior:
            time_stamp = int(time.time() * 1000)
            behavior = await behavior_decision(work_path, prompt, True, time_stamp)

        if(behavior["type"] == '2'):
            new_prompt = prompts.image_generation_proactive.format(task=config.task_content, context=behavior["context"])
            result = await text2Image(work_path, new_prompt)
        else:
            dialog_history = utils.get_dialog(work_path, prompt, True, time_stamp)
            dialog_history_str = ""
            for item in dialog_history:
                if item.get("type") == "text":
                    dialog_history_str += item.get("text") + "\n\n"
            
            operation_history = utils.get_operation(work_path, True, time_stamp)
            operation_history_str = ""
            for item in operation_history:
                operation_history_str += item.get("text") + "\n\n"
                
            attitude_history = utils.get_attitude(work_path, True, time_stamp)
            attitude_history_str = ""
            for item in attitude_history:
                attitude_history_str += item.get("text") + "\n\n"
            
            system_prompt = prompts.system_DISC_generation_proactive.format(task=config.task_content)
            user_prompt = prompts.user_generation_proactive.format(context=behavior["context"], dialog_history=dialog_history_str, operation_history=operation_history_str, attitude_history=attitude_history_str)
            msg = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            response = await gpt_temp(msg)
            result = {"text": response, "image":""}
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        result["time_stamp"] = timestamp
        result["behavior"] = behavior
        future.set_result(result)
    except Exception as e:
        future.set_exception(e)

async def behavior_decision(work_path, prompt, server, current_time):
    # get three types of history info
    dialog_history = utils.get_dialog(work_path, prompt, server, current_time)
    operation_history = utils.get_operation(work_path, server, current_time)
    
    # organize system and user prompt
    if server == False:
        type_decision_system = prompts.system_generation_type_decision_reactive.format(task=config.task_content)
        type_decision_user = prompts.user_generation_type_decision_reactive.format(dialog_history=dialog_history, user_question = prompt)
        context_conclusion_system = prompts.system_context_conclusion_reactive.format(task=config.task_content)
        context_conclusion_user = prompts.user_context_conclusion_reactive.format(dialog_history=dialog_history, operation_history=operation_history, user_question = prompt)
    else:
        type_decision_system = prompts.system_generation_type_decision_proactive.format(task=config.task_content)
        type_decision_user = prompts.user_generation_type_decision_proactive.format(dialog_history=dialog_history)
        context_conclusion_system = prompts.system_context_conclusion_proactive.format(task=config.task_content)
        context_conclusion_user = prompts.user_context_conclusion_proactive.format(dialog_history=dialog_history, operation_history=operation_history)
    
    msg_for_type_decision = [
        {
            "role": "system",
            "content": type_decision_system
        },
        {
            "role": "user",
            "content": type_decision_user
        }
    ]
    
    msg_for_context_conclusion = [
        {
            "role": "system",
            "content": context_conclusion_system
        },
        {
            "role": "user",
            "content": context_conclusion_user
        }
    ]
    
    msgs = [msg_for_type_decision, msg_for_context_conclusion]
    
    start_time = time.time()
    responses = await gpt_temp_multi(msgs)
    end_time = time.time()
    print(f"简化后的behavior decision耗时：{end_time - start_time:.2f}秒")
    print(f"behavior decision生成结果：{responses}")
    
    behavior_decision = {
        "type": responses[0],
        "context": responses[1]
    }
    
    return behavior_decision

async def get_attitude_analysis(work_path, prompt):
    print(f"问题：{prompt}")
    msg = [{
            "role": "user",
            "content": f"{prompt}"
            }]
    response = await gpt_temp(msg)
    return {"text": response}

async def get_operation_analysis(work_path, message, timestamp):
    # 列出screenshots/canvas下的所有文件
    canvas_path = os.path.join(work_path, "screenshot", "canvas")
    canvas_files = os.listdir(canvas_path)
    # 去掉所有文件的后缀
    files = [os.path.splitext(file)[0] for file in canvas_files]
    # 将文件名按照数字大小排序
    files = sorted(files, key=lambda x: int(x))
    last_data2 = None
    if len(files) > 1:
        timestamp2 = files[-2]
        last_data2 = {
            "canvas": os.path.join(work_path, "screenshot", "canvas", f"{timestamp2}.jpg"),
            "bbox": os.path.join(work_path, "screenshot", "bbox", f"{timestamp2}.jpg")
        }
    last_data1 = {
        "message": message,
        "time_stamp": timestamp,
        "canvas": os.path.join(work_path, "screenshot", "canvas", f"{timestamp}.jpg"),
        "bbox": os.path.join(work_path, "screenshot", "bbox", f"{timestamp}.jpg")
    }
    print("last_data1:", last_data1)
    print("last_data2:", last_data2)
    operation = utils.get_operation_data(last_data1, last_data2)
    system_msg = [{'type': 'text', 'text': utils.prompt_format(prompts.prompt_for_operation_analysis.format(task=config.task_content))}]
    msg = [
        {
            "role": "system",
            "content": system_msg
        },
        {
            "role": "user",
            "content": operation
        }]
    response = await gpt_temp(msg, json_format=False)
    return response
