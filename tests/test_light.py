import RPi.GPIO as GPIO
import time
import sys

LIGHT_PIN = 13

def main():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LIGHT_PIN, GPIO.IN)

    print("==================================================")
    print("  💡 디지털 조도 센서(BCM 13) 입력 디버거 가동")
    print("  종료하려면 Ctrl+C를 누르십시오.")
    print("==================================================")
    
    try:
        while True:
            raw_val = GPIO.input(LIGHT_PIN)
            val = 0 if raw_val else 1  # 논리 반전 적용
            status = "어두움 (1)" if val == 1 else "밝음 (0)"
            print(f"[{time.strftime('%H:%M:%S')}] 원시 신호: {raw_val} -> 반전 적용: {val} ({status})", end="\r")
            sys.stdout.flush()
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n디버깅을 종료합니다. 자원을 정리합니다.")
    finally:
        # 이 핀만 자원 정리하여 다른 핀 구동 방해 최소화
        try:
            GPIO.cleanup(LIGHT_PIN)
        except Exception:
            pass

if __name__ == "__main__":
    main()
