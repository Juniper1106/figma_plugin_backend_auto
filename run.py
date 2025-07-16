# run.py
from app import app
from app import socketio
import app.utils as utils
from app.routes import proactive_conclude, proactive_chat

if __name__ == '__main__':
    # app.run(debug=True, host="0.0.0.0", port=5010)
    # socketio.start_background_task(proactive_conclude)  # 启动后台任务
    # socketio.start_background_task(proactive_chat)  # 启动后台任务
    socketio.run(app, debug=False, host="0.0.0.0", port=5010)