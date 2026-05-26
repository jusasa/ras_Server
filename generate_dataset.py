import sqlite3
import random
from datetime import datetime, timedelta

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

def generate_data(num_samples=1200):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    start_time = datetime.now() - timedelta(hours=24)
    records = []
    
    # 3가지 라벨에 대한 균등한 샘플 생성
    samples_per_class = num_samples // 3
    
    # 1. 라벨 0 : 안정 상태 (생활 반응 정상)
    for i in range(samples_per_class):
        timestamp = (start_time + timedelta(seconds=i*2)).strftime("%Y-%m-%d %H:%M:%S")
        temp = round(random.uniform(19.0, 27.0), 1)
        hum = round(random.uniform(35.0, 65.0), 1)
        dist = round(random.uniform(50.0, 140.0), 1)
        motion = 1 if random.random() < 0.3 else 0  # 이따금 움직임 감지
        is_dark = 1 if random.random() < 0.4 else 0
        records.append((timestamp, temp, hum, dist, motion, is_dark, 0))
        
    # 2. 라벨 1 : 교감 상태 (상호작용 유도)
    for i in range(samples_per_class):
        timestamp = (start_time + timedelta(seconds=(samples_per_class + i)*2)).strftime("%Y-%m-%d %H:%M:%S")
        temp = round(random.uniform(20.0, 27.0), 1)
        hum = round(random.uniform(35.0, 60.0), 1)
        dist = round(random.uniform(5.0, 39.0), 1)      # 40cm 이내 근접
        motion = 1 if random.random() < 0.9 else 0     # 활발한 움직임
        is_dark = 0                                    # 보통 밝을 때 교감
        records.append((timestamp, temp, hum, dist, motion, is_dark, 1))

    # 3. 라벨 2 : 이상 징후 (장시간 무반응 또는 극한 환경)
    for i in range(samples_per_class):
        timestamp = (start_time + timedelta(seconds=(samples_per_class * 2 + i)*2)).strftime("%Y-%m-%d %H:%M:%S")
        # 50% 확률로 온습도 이상 / 50% 확률로 장시간 고독 상태(무반응)
        if random.random() < 0.5:
            # 극한 환경 위험
            if random.random() < 0.5:
                temp = round(random.uniform(35.5, 42.0), 1)  # 폭염/화재 의심 고온
                hum = round(random.uniform(75.0, 95.0), 1)   # 고습
            else:
                temp = round(random.uniform(5.0, 10.0), 1)   # 한파 의심 저온
                hum = round(random.uniform(10.0, 20.0), 1)   # 건조
            dist = round(random.uniform(50.0, 180.0), 1)
            motion = 1 if random.random() < 0.2 else 0
        else:
            # 고독 위험 (PIR 무반응 및 부재)
            temp = round(random.uniform(19.0, 26.0), 1)
            hum = round(random.uniform(35.0, 60.0), 1)
            dist = round(random.uniform(150.0, 200.0), 1)   # 거리 멀거나 없음
            motion = 0                                     # 움직임 전혀 없음
        is_dark = 1 if random.random() < 0.5 else 0
        records.append((timestamp, temp, hum, dist, motion, is_dark, 2))

    # 데이터베이스에 삽입
    cursor.executemany('''
        INSERT INTO care_logs (timestamp, temperature, humidity, distance, motion, is_dark, label)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', records)
    
    conn.commit()
    conn.close()
    print(f"가상 센서 데이터 및 라벨 생성 완료: {num_samples}개 행이 {DB_NAME}에 추가되었습니다.")

if __name__ == "__main__":
    generate_data()
