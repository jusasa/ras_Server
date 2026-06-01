import sqlite3
import asyncio
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import uvicorn

from src.hardware import HardwareController
# from src.ai_engine import EdgeAIEngine # 나중에 TFLite 모델 완성되면 주석 해제

app = FastAPI()
templates = Jinja2Templates(directory="templates")
hw = HardwareController()

# DB 초기화
def init_db():
    conn = sqlite3.connect('sensor_dataset.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp REAL,
                  gas INTEGER,
                  temperature REAL,
                  humidity REAL,
                  distance_cm REAL,
                  is_closed BOOLEAN)''')
    conn.commit()
    conn.close()

init_db()

# 백그라운드 데이터 수집 Task (1초마다 실행)
async def collect_data_loop():
    while True:
        data = hw.get_sensor_data()
        
        # 뚜껑이 닫혀있을 때만 데이터를 저장하고 AI 추론 (오탐 방지)
        if data['is_closed']:
            conn = sqlite3.connect('sensor_dataset.db')
            c = conn.cursor()
            c.execute("INSERT INTO sensor_data (timestamp, gas, temperature, humidity, distance_cm, is_closed) VALUES (?, ?, ?, ?, ?, ?)",
                      (data['timestamp'], data['gas'], data['temperature'], data['humidity'], data['distance_cm'], data['is_closed']))
            conn.commit()
            conn.close()
            
            # TODO: AI 엔진 추론 및 LED/서보 제어 로직 추가 예정
            print(f"[DB 저장 완료] {data}")
        else:
            print("[대기] 뚜껑이 열려 있어 데이터를 무시합니다.")
            
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    # 서버 켜질 때 백그라운드 데이터 수집 루프 시작
    asyncio.create_task(collect_data_loop())

@app.get("/")
async def read_dashboard(request: Request):
    # 대시보드 렌더링
    return templates.TemplateResponse("dashboard.html", {"request": request})

if __name__ == "__main__":
    # uvicorn 서버 실행 (포트 8000)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)