import sqlite3
import asyncio
import json
import logging
import os
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
import uvicorn
import paho.mqtt.client as mqtt

from src.hardware import HardwareController
from src.ai_engine import TFLiteEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sensor_dataset.db')

# 로그 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 컨트롤러 및 AI 엔진 초기화 (중복 임포트 및 핀 점유 충돌 방지를 위해 지연 생성)
hw = None
ai_engine = None

# 전역 상태 변수
current_label = None        # 현재 수집 중인 데이터 라벨 (None이면 수집 안 함)
connected_websockets = []   # 연결된 WebSocket 클라이언트 목록
loop = None                 # asyncio 이벤트 루프 참조용

# MQTT 설정
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_SUB_TOPIC = "smart_ecobin/control"
MQTT_PUB_SENSOR_TOPIC = "smart_ecobin/sensor"
MQTT_PUB_AI_TOPIC = "smart_ecobin/ai_status"

mqtt_client = None

# DB 초기화 (label 컬럼 추가)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp REAL,
                  gas INTEGER,
                  temperature REAL,
                  humidity REAL,
                  distance_cm REAL,
                  is_closed BOOLEAN,
                  label INTEGER DEFAULT NULL)''')
    conn.commit()
    conn.close()

init_db()

# MQTT Callback 함수 정의
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("[MQTT 연결 성공] 브로커에 정상 연결되었습니다.")
        client.subscribe(MQTT_SUB_TOPIC)
        logger.info(f"[MQTT 구독 시작] 토픽: {MQTT_SUB_TOPIC}")
    else:
        logger.error(f"[MQTT 연결 실패] 결과 코드: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        logger.info(f"[MQTT 메시지 수신] 토픽: {msg.topic}, 내용: {payload}")
        data = json.loads(payload)
        
        # 제어 명령 처리
        if "action" in data:
            action = data["action"]
            if action == "ventilate":
                logger.info("[MQTT 제어 명령] 강제 환기(서보모터) 가동 요청 수신")
                if loop:
                    # 블로킹 하드웨어 제어는 별도 스레드에서 비동기로 실행
                    loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(asyncio.to_thread(hw.run_ventilation))
                    )
            
        if "led" in data:
            led_status = data["led"]
            if led_status in ["NORMAL", "WARNING", "DANGER"]:
                logger.info(f"[MQTT 제어 명령] LED 상태 설정 요청 수신: {led_status}")
                if loop:
                    loop.call_soon_threadsafe(
                        lambda: hw.set_status_led(led_status)
                    )
    except Exception as e:
        logger.error(f"[MQTT 메시지 처리 에러]: {e}", exc_info=True)

# MQTT 클라이언트 시작 함수
def start_mqtt():
    global mqtt_client
    try:
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"[MQTT 초기화 실패]: {e}", exc_info=True)

# WebSocket 클라이언트 브로드캐스트
async def broadcast_to_websockets(message_dict):
    disconnected_sockets = []
    message_json = json.dumps(message_dict)
    for websocket in connected_websockets:
        try:
            await websocket.send_text(message_json)
        except WebSocketDisconnect:
            disconnected_sockets.append(websocket)
        except Exception as e:
            logger.error(f"[WebSocket 전송 에러]: {e}")
            disconnected_sockets.append(websocket)
            
    for ws in disconnected_sockets:
        if ws in connected_websockets:
            connected_websockets.remove(ws)

# 백그라운드 데이터 수집 Task (1초마다 실행)
async def collect_data_loop():
    global current_label
    fan_cool_down = 0 # 환기 연속 작동 방지 쿨다운
    
    while True:
        try:
            # 1. 하드웨어로부터 센서 데이터 수집
            data = hw.get_sensor_data()
            
            # 2. AI 엔진을 통한 상태 판단 및 제어 명령 추론
            ai_decision = ai_engine.predict(data)
            
            # 3. AI 판단에 따른 실시간 하드웨어 작동 제어
            # LED 지시등 상태 업데이트
            hw.set_status_led(ai_decision["status"])
            
            # 위험 상태(DANGER)이고 환기 작동이 필요하며 쿨다운이 끝났을 경우 서보모터 구동
            if ai_decision["run_fan"] and fan_cool_down <= 0:
                logger.info("[AI 판단] 위험 감지! 강제 환기용 서보모터를 구동합니다.")
                asyncio.create_task(asyncio.to_thread(hw.run_ventilation))
                fan_cool_down = 10 # 10초 쿨다운 지정 (반복 모터 구동 방어)
            
            if fan_cool_down > 0:
                fan_cool_down -= 1
            
            # 4. 뚜껑이 닫혀있을 때만 수집 데이터 DB 적재 (수집 모드 활성화 시에만 또는 평시에도 저장 여부 결정)
            # 여기서는 뚜껑이 닫혀 있고 current_label이 설정되어 있을 때 데이터를 라벨과 함께 저장하도록 함
            if data['is_closed']:
                if current_label is not None:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("""INSERT INTO sensor_data 
                                 (timestamp, gas, temperature, humidity, distance_cm, is_closed, label) 
                                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                              (data['timestamp'], data['gas'], data['temperature'], data['humidity'], 
                               data['distance_cm'], data['is_closed'], current_label))
                    conn.commit()
                    conn.close()
                    logger.info(f"[DB 저장 완료 (라벨 {current_label})] {data}")
            else:
                logger.debug("[대기] 뚜껑이 열려 있어 데이터가 무시되거나 AI 판단만 수행합니다.")
            
            # 5. MQTT 브로커로 센서 데이터 및 AI 상태 발행 (Publish)
            if mqtt_client and mqtt_client.is_connected():
                # 센서 데이터 발행
                mqtt_client.publish(MQTT_PUB_SENSOR_TOPIC, json.dumps(data))
                # AI 의사결정 상태 발행
                mqtt_client.publish(MQTT_PUB_AI_TOPIC, json.dumps(ai_decision))
            
            # 6. 연결된 모든 웹 대시보드로 데이터 브로드캐스트
            payload = {
                "sensors": {
                    "gas": data["gas"],
                    "temperature": data["temperature"],
                    "humidity": data["humidity"],
                    "distance_cm": data["distance_cm"],
                    "is_closed": data["is_closed"]
                },
                "ai_decision": ai_decision,
                "collecting_label": current_label
            }
            await broadcast_to_websockets(payload)
            
        except Exception as e:
            logger.error(f"[백그라운드 루프 에러]: {e}", exc_info=True)
            
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    global loop, hw, ai_engine
    loop = asyncio.get_running_loop()
    
    # 지연 로딩: uvicorn 중복 임포트 시 핀 점유 충돌을 막기 위해 FastAPI 스타트업 시점에 최초 1회만 초기화합니다.
    hw = HardwareController()
    ai_engine = TFLiteEngine()
    
    # MQTT 클라이언트 스레드 시작
    start_mqtt()
    # 백그라운드 데이터 수집 루프 가동
    asyncio.create_task(collect_data_loop())

@app.on_event("shutdown")
async def shutdown_event():
    global mqtt_client
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logger.info("[MQTT 연결 해제] 안전하게 종료되었습니다.")

# 대시보드 메인 페이지 렌더링
@app.get("/")
async def read_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

# 데이터 수집 시작 API
@app.get("/api/record/start/{label}")
async def start_recording(label: int):
    global current_label
    current_label = label
    logger.info(f"[데이터 수집 시작] 수집 중인 라벨 설정: {current_label}")
    return {"status": "success", "collecting_label": current_label}

# 데이터 수집 중지 API
@app.get("/api/record/stop")
async def stop_recording():
    global current_label
    logger.info(f"[데이터 수집 중지] 최종 수집 중단 라벨: {current_label}")
    current_label = None
    return {"status": "success", "collecting_label": None}

# 수동 환기 가동 API (HTTP 트리거)
@app.get("/api/control/ventilate")
async def control_ventilate():
    logger.info("[원격 제어] API를 통한 수동 강제 환기 명령 실행")
    asyncio.create_task(asyncio.to_thread(hw.run_ventilation))
    # 제어 이벤트를 MQTT로도 발행하여 다른 구독 기기들에 알림
    if mqtt_client and mqtt_client.is_connected():
        mqtt_client.publish(MQTT_PUB_AI_TOPIC, json.dumps({"status": "MANUAL_CONTROL", "ai_status": "사용자에 의한 수동 환기 작동", "run_fan": True}))
    return {"status": "success", "message": "Ventilation started"}

# WebSocket 엔드포인트
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    logger.info(f"[WebSocket 연결됨] 현재 클라이언트 수: {len(connected_websockets)}")
    try:
        while True:
            # 클라이언트로부터 메시지 대기 (연결 유지용 ping/pong 등 처리)
            data = await websocket.receive_text()
            # 필요 시 클라이언트 측에서 보내는 커스텀 명령 처리 가능
    except WebSocketDisconnect:
        logger.info("[WebSocket 연결 종료]")
    finally:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
        logger.info(f"현재 클라이언트 수: {len(connected_websockets)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)