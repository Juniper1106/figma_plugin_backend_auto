# app/__init__.py
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from sentence_transformers import SentenceTransformer
import os

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*')  # 允许所有 WebSocket 来源
os.environ["TOKENIZERS_PARALLELISM"] = "false"
model = SentenceTransformer('paraphrase-MiniLM-L6-v2')

from app import routes
