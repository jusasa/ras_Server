# export_to_csv.py
import sqlite3
import csv

DB_NAME = "sensor_dataset.db"
CSV_NAME = "sensor_dataset.csv"

def export_db_to_csv():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 조도센서를 제외한 핵심 feature 4개와 정답 라벨 추출
    query = "SELECT temperature, humidity, distance, motion, label FROM care_logs"
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print("DB에 추출할 데이터가 없습니다.")
        conn.close()
        return
        
    # CSV 파일 쓰기
    with open(CSV_NAME, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # 텐서플로우 데이터셋 매핑용 헤더 작성
        writer.writerow(['temperature', 'humidity', 'distance', 'motion', 'label'])
        # 데이터 대량 주입
        writer.writerows(rows)
        
    conn.close()
    print(f"추출 완료: {CSV_NAME} (총 {len(rows)}개 데이터셋 레코드)")

if __name__ == "__main__":
    export_db_to_csv()
