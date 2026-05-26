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
        CREATE TABLE IF NOT EXISTS care_logs (
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
                # 1. 비동기 하드웨어 센서 판독 (2초 타임아웃 방어)
                sensor_data = await asyncio.wait_for(
                    asyncio.to_thread(hw_controller.read_sensors),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                logging.warning("[하드웨어 경고] 센서 무응답(타임아웃)! 배선 혹은 전원을 확인하세요. 기본 안전값으로 대체합니다.")
                sensor_data = {
                    "temperature": 0.0,
                    "humidity": 0.0,
                    "distance": 200.0,
                    "motion": 0,
                    "is_dark": 0
                }

            # 1-1. Thom의 불쾌지수(DI) 기반 쾌적도(Comfort Score) 산출
            temp = sensor_data["temperature"]
            hum = sensor_data["humidity"]
            di = 0.81 * temp + 0.01 * hum * (0.99 * temp - 14.3) + 46.3

            if 60.0 <= di <= 68.0:
                comfort_score = 100.0
            elif di > 68.0:
                comfort_score = max(0.0, 100.0 - (di - 68.0) * (100.0 / (83.0 - 68.0)))
            else:  # di < 60.0
                comfort_score = max(0.0, 100.0 - (60.0 - di) * (100.0 / (60.0 - 45.0)))

            sensor_data["comfort_score"] = int(round(comfort_score))
            sensor_data["comfort_index"] = round(di, 1)

            # 2. TFLite AI 모델 추론 및 액추에이터 제어 명령 수립
            ai_decision = await asyncio.to_thread(ai_engine.predict, sensor_data)
            await asyncio.to_thread(hw_controller.control_leds, ai_decision, sensor_data["is_dark"])

            # 3. 실시간 센서 및 AI 상태 추적 로깅 (1초 주기)
            logging.info(
                f"[센서 추적] 온도: {sensor_data['temperature']}°C | "
                f"습도: {sensor_data['humidity']}% | "
                f"쾌적도: {sensor_data['comfort_score']}% | "
                f"거리: {sensor_data['distance']}cm | "
                f"모션: {sensor_data['motion']} | "
                f"조도: {sensor_data['is_dark']} | "
                f"상태: {ai_decision['ai_status']}"
            )

            # 4. 실시간 웹 브로드캐스팅
            payload = {
                "sensors": sensor_data,
                "ai_decision": ai_decision,
                "collecting_label": current_label
            }
            await ws_manager.broadcast(payload)

            # 5. 수집 모드 시 DB 기록
            if current_label is not None:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute('''
                    INSERT INTO care_logs (timestamp, temperature, humidity, distance, motion, is_dark, label)
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
                logging.info(f"[DB 로깅] 돌봄 라벨 {current_label} 기록 완료 -> (거리: {sensor_data['distance']}cm)")

        except Exception as e:
            logging.error(f"[메인 루프 에러] 시스템 예외 발생: {e}", exc_info=True)

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
