import logging
from logging.handlers import RotatingFileHandler
import os

# Configure logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE_PATH = os.path.join(LOG_DIR, "app.log")

# Setup root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s:%(lineno)d] - %(message)s'
)

# Stream handler for console
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
root_logger.addHandler(stream_handler)

# Rotating File Handler (Max 100MB)
file_handler = RotatingFileHandler(
    LOG_FILE_PATH,
    maxBytes=100 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

# Standard imports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio
import sqlite3
from datetime import datetime

from src.hardware import HardwareController
from src.ai_engine import TFLiteEngine

hw_controller = None
ai_engine = None

current_label = None
DB_NAME = "sensor_dataset.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            temperature REAL,
            humidity REAL,
            distance REAL,
            motion INTEGER,
            is_dark INTEGER,
            label INTEGER
        )
    ''')
    conn.commit()
    conn.close()

class WebSocketManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = WebSocketManager()

async def sensor_ai_loop():
    global current_label
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    while True:
        try:
            try:
                sensor_data = await asyncio.wait_for(
                    asyncio.to_thread(hw_controller.read_sensors),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                logging.warning("[하드웨어 경고] 센서 무응답(타임아웃)! 배선을 확인하세요. 기본값을 반환합니다.")
                sensor_data = {
                    "temperature": 0.0,
                    "humidity": 0.0,
                    "distance": 200.0,
                    "motion": 0,
                    "is_dark": 0
                }

            ai_decision = await asyncio.to_thread(ai_engine.predict, sensor_data)
            await asyncio.to_thread(hw_controller.control_leds, ai_decision)

            payload = {
                "sensors": sensor_data,
                "ai_decision": ai_decision,
                "collecting_label": current_label
            }
            await ws_manager.broadcast(payload)

            if current_label is not None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    INSERT INTO sensor_logs (timestamp, temperature, humidity, distance, motion, is_dark, label)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    current_time,
                    sensor_data['temperature'],
                    sensor_data['humidity'],
                    sensor_data['distance'],
                    sensor_data['motion'],
                    sensor_data['is_dark'],
                    current_label
                ))
                conn.commit()
                logging.info(f"[DB 로깅] 돌봄 라벨 {current_label} 기록 중... (거리: {sensor_data['distance']}cm)")

        except Exception as e:
            logging.error(f"Loop Error: {e}", exc_info=True)

        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global hw_controller, ai_engine
    init_db()
    hw_controller = HardwareController()
    ai_engine = TFLiteEngine()
    task = asyncio.create_task(sensor_ai_loop())
    yield
    task.cancel()
    hw_controller.cleanup()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def get_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

@app.get("/api/record/start/{label}")
async def start_recording(label: int):
    global current_label
    current_label = label
    return {"status": "success", "message": f"돌봄 라벨 {label} 기록 시작"}

@app.get("/api/record/stop")
async def stop_recording():
    global current_label
    current_label = None
    return {"status": "success", "message": "돌봄 기록 중지"}
