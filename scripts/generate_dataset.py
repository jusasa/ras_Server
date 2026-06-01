import sqlite3
import random
import time
from datetime import datetime, timedelta
import os

# Project root path resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, "sensor_dataset.db")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # main.py에서 생성하는 테이블 구조와 완벽 호환되게 설정
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            gas INTEGER,
            temperature REAL,
            humidity REAL,
            distance_cm REAL,
            is_closed BOOLEAN,
            label INTEGER DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()

def generate_data(num_samples=1200):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 기존 데이터 삭제 (새로 학습 셋 구성)
    cursor.execute("DELETE FROM sensor_data")
    conn.commit()
    
    base_time = time.time() - (24 * 3600) # 24시간 전부터 시작
    records = []
    
    # 3가지 라벨에 대한 균등한 샘플 생성
    samples_per_class = num_samples // 3
    
    # 1. 라벨 0 : 정상 상태 (부패도 낮음 / 쾌적함)
    for i in range(samples_per_class):
        timestamp = base_time + (i * 2)
        gas = random.randint(50, 250)
        temp = round(random.uniform(18.0, 25.0), 1)
        hum = round(random.uniform(30.0, 55.0), 1)
        dist = round(random.uniform(20.0, 28.0), 1) # 쓰레기 조금 들어있음
        is_closed = True
        records.append((timestamp, gas, temp, hum, dist, is_closed, 0))
        
    # 2. 라벨 1 : 주의 상태 (약간의 악취 / 부패 우려)
    for i in range(samples_per_class):
        timestamp = base_time + (samples_per_class + i) * 2
        gas = random.randint(250, 450)
        temp = round(random.uniform(25.0, 30.0), 1)
        hum = round(random.uniform(55.0, 70.0), 1)
        dist = round(random.uniform(10.0, 20.0), 1) # 절반 이하로 참
        is_closed = True
        records.append((timestamp, gas, temp, hum, dist, is_closed, 1))
 
    # 3. 라벨 2 : 위험 상태 (고농도 가스 및 악취 / 환기 필요)
    for i in range(samples_per_class):
        timestamp = base_time + (samples_per_class * 2 + i) * 2
        # 고온 다습 또는 가스 대량 방출
        if random.random() < 0.5:
            gas = random.randint(450, 950)
            temp = round(random.uniform(30.0, 38.0), 1)
            hum = round(random.uniform(70.0, 90.0), 1)
            dist = round(random.uniform(2.0, 15.0), 1)
        else:
            # 쓰레기가 꽉 참 (적재도 위험)
            gas = random.randint(300, 600)
            temp = round(random.uniform(22.0, 28.0), 1)
            hum = round(random.uniform(40.0, 65.0), 1)
            dist = round(random.uniform(1.0, 8.0), 1) # 쓰레기 꽉 참
        is_closed = True
        records.append((timestamp, gas, temp, hum, dist, is_closed, 2))

    # 데이터베이스에 삽입
    cursor.executemany('''
        INSERT INTO sensor_data (timestamp, gas, temperature, humidity, distance_cm, is_closed, label)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', records)
    
    conn.commit()
    conn.close()
    print(f"[데이터 생성 완료] {num_samples}개의 Smart Eco-Bin 가상 학습 레코드가 DB에 기록되었습니다.")

if __name__ == "__main__":
    generate_data()
