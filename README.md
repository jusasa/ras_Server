# Smart Eco-Bin: 다중 센서 융합 및 엣지 컴퓨팅 기반 밀폐공간 위생 관제 플랫폼

## 💡 프로젝트 개요 (Project Overview)
본 프로젝트는 1인 가구 및 상주 관리자가 없는 무인 매장의 여름철 악취 및 위생 문제를 해결하기 위한 **지능형 AIoT 위생 관제 시스템**입니다. 
라즈베리파이 기반의 엣지 컴퓨팅(Edge Computing) 아키텍처를 도입하여 다중 센서(가스, 온습도, 거리, 스위치) 데이터를 수집하고, 독립된 AI 엔진이 부패 위험도를 실시간으로 추론하여 하드웨어 제어 및 웹 대시보드 모니터링을 제공합니다.

* **개발 기간:** 2026년 5월 ~ 6월
* **소속:** 컴퓨터시스템공학과
* **담당자:** 서석민

## 🏗️ 시스템 아키텍처 (System Architecture)
본 시스템은 하드웨어 제어부와 웹 서버 간의 완벽한 분리(Decoupling)를 목표로 설계되었습니다.

1. **Layer 1 (Embedded & Sensor):** 센서 데이터 계측 및 액추에이터 제어 (Python `gpiozero`, `spidev`)
2. **Layer 2 (Backend Server):** 비동기 REST API 및 로컬 DB 적재 (`FastAPI`, `SQLite`)
3. **Layer 3 (Edge AI Engine):** 다변량 데이터 기반 부패도 3단계 분류 추론 (`Scikit-learn` / `TFLite`)
4. **Layer 4 (Web Dashboard):** 실시간 센서 시각화 및 양방향 하드웨어 원격 제어 (`HTML`, `Chart.js`, `WebSocket`)

## 🔌 하드웨어 구성 및 핀 맵 (Pin Map)
* **메인 보드:** Raspberry Pi 4 + ADC 내장 Shield Board (12-bit ADC 지원)

| 부품명 | 용도 | 연결 핀 (라즈베리파이/쉴드) |
| :--- | :--- | :--- |
| **MQ-6** | 부패 가스 및 악취 농도 측정 | `ADC A0` (Analog) |
| **MQ-6** | 부패 가스 및 악취 농도 측정 | `ADC A1` (Analog) |
| **MQ-6** | 부패 가스 및 악취 농도 측정 | `ADC A2` (Analog) |
| **DHT11** | 내부 온도 및 습도 측정 | `GPIO 21` |
| **HC-SR04** | 쓰레기 적재량(거리) 측정 | Trig: `GPIO 17`, Echo: `GPIO 18` |
| **Limit Switch** | 뚜껑 개폐 여부 (오탐 방지) | `GPIO 13` |
| **Servo Motor** | 강제 환기/탈취 동작 시연용 | `GPIO 6` |
| **LED 1 (Green)** | 상태 표시 (정상) | `GPIO 19` |
| **LED 2 (Yellow)** | 상태 표시 (주의) | `GPIO 26` |
| **LED 3 (Red)** | 상태 표시 (위험) | `GPIO 16` |
| **LED 4 (Blue)** | 액추에이터 작동 확인 | `GPIO 20` |

## 📁 디렉토리 구조 (Directory Structure)
```text
term-project/
├── main.py                # FastAPI 웹 서버 및 백그라운드 데이터 수집 메인 루프
├── models/
│   └── edge_model.tflite  # 학습 완료된 초경량 Edge AI 추론 모델 파일
├── requirements.txt       # Python 패키지 의존성 목록
├── sensor_dataset.csv     # 추출된 학습용 원시 데이터 (센서 로그)
├── sensor_dataset.db      # 실시간 센서 데이터가 적재되는 로컬 SQLite DB
├── system_documentation.md # 시스템 아키텍처, 플로우차트 및 핀 맵 명세서
├── src/
│   ├── ai_engine.py       # TFLite 모델 로드 및 실시간 추론(Inference) 클래스
│   └── hardware.py        # 하드웨어 핀 제어 및 센서 데이터 수집 캡슐화 클래스
├── templates/
│   └── dashboard.html     # 실시간 관제 및 원격 제어 프론트엔드 UI (Chart.js)
├── scripts/
│   ├── db_to_csv.py       # SQLite DB 데이터를 CSV로 추출하는 스크립트 (학습 데이터 생성용)
│   └── generate_dataset.py # 학습용 가상 센서 데이터를 생성하여 DB에 주입하는 스크립트
└── tests/
    └── test_error.py      # 에러 예외 처리 및 백엔드 안정성 시뮬레이션 테스트
```

## ⚙️ 실행 및 테스트 방법 (How to Run & Test)
* **백엔드 서버 실행:**
  ```bash
  python main.py
  ```
* **학습용 가상 데이터 생성:**
  ```bash
  python scripts/generate_dataset.py
  ```
* **데이터셋 CSV 추출 (학습용):**
  ```bash
  python scripts/db_to_csv.py
  ```
* **에러 예외 처리 테스트 (QA 시뮬레이터):**
  ```bash
  python tests/test_error.py
  ```