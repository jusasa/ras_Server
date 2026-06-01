import time
import random
import logging

logger = logging.getLogger(__name__)

# 하드웨어 드라이버 임포트 방어막 (일반 PC 개발 환경 지원용)
HAS_HARDWARE = True

try:
    import spidev
except ImportError:
    logger.warning("[하드웨어 알림] spidev 라이브러리가 없어 가상 SPI 모드로 동작합니다.")
    HAS_HARDWARE = False

try:
    import Adafruit_DHT
except ImportError:
    logger.warning("[하드웨어 알림] Adafruit_DHT 라이브러리가 없어 가상 DHT11 온습도 센서로 동작합니다.")
    HAS_HARDWARE = False

try:
    from gpiozero import DistanceSensor, Button, Servo, LED
except ImportError:
    logger.warning("[하드웨어 알림] gpiozero 라이브러리가 없어 가상 GPIO 핀 및 액추에이터로 동작합니다.")
    HAS_HARDWARE = False


class HardwareController:
    def __init__(self):
        self.has_hw = HAS_HARDWARE
        
        if self.has_hw:
            try:
                # 1. 가스 센서 (MQ-6) - ADC 0번 채널 (A0)
                self.spi = spidev.SpiDev()
                self.spi.open(0, 0)
                self.spi.max_speed_hz = 1350000
                
                # 2. 온습도 센서 (DHT11) - GPIO 21
                self.dht_sensor = Adafruit_DHT.DHT11
                self.dht_pin = 21
                
                # 3. 초음파 센서 (HC-SR04) - Trig: 17, Echo: 18
                self.ultrasonic = DistanceSensor(echo=18, trigger=17, max_distance=2.0)
                
                # 4. 리미트 스위치 (뚜껑 닫힘 감지) - GPIO 13
                self.limit_switch = Button(13, pull_up=True)
                
                # 5. 서보 모터 (강제 환기 또는 탈취제 분사) - GPIO 6
                self.servo = Servo(6)
                
                # 6. 상태 표시 LED (19, 26, 16, 20)
                self.led_normal = LED(19)   # 초록 (정상)
                self.led_warning = LED(26)  # 노랑 (주의)
                self.led_danger = LED(16)   # 빨강 (위험)
                self.led_action = LED(20)   # 파랑 (팬/서보 작동 표시)
            except Exception as e:
                logger.error(f"[하드웨어 초기화 실패] 에러: {e}. 가상 시뮬레이션 모드로 강제 전환합니다.")
                self.has_hw = False

    def read_gas(self):
        if not self.has_hw:
            # 가상 환경: 50 ~ 750 사이의 값 반환 (가상 변화 부여)
            return random.randint(100, 350)
            
        try:
            # MCP3208(12bit) 기준 A0 채널 읽기
            adc = self.spi.xfer2([6 | (0 & 4) >> 2, (0 & 3) << 6, 0])
            data = ((adc[1] & 15) << 8) + adc[2]
            return data
        except Exception:
            return 120 # 에러 발생 시 기본값

    def get_sensor_data(self):
        """모든 센서 데이터를 딕셔너리로 반환"""
        if not self.has_hw:
            # 가상 데이터 생성 (변동성 연출)
            gas = self.read_gas()
            temperature = round(random.uniform(22.0, 27.5), 1)
            humidity = round(random.uniform(40.0, 65.0), 1)
            distance = round(random.uniform(5.0, 28.0), 1)
            is_closed = True # 테스트 편의상 항상 닫힘 상태로 시뮬레이션
            
            return {
                "gas": gas,
                "temperature": temperature,
                "humidity": humidity,
                "distance_cm": distance,
                "is_closed": is_closed,
                "timestamp": time.time()
            }
            
        try:
            gas = self.read_gas()
            humidity, temperature = Adafruit_DHT.read_retry(self.dht_sensor, self.dht_pin)
            distance = self.ultrasonic.distance * 100 # cm 단위 변환
            is_closed = self.limit_switch.is_pressed # True면 닫힘, False면 열림
            
            if humidity is None or temperature is None:
                humidity, temperature = 0, 0

            return {
                "gas": gas,
                "temperature": temperature,
                "humidity": humidity,
                "distance_cm": round(distance, 1),
                "is_closed": is_closed,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"[센서 계측 실패] 기본 안전 데이터 반환. 에러: {e}")
            return {
                "gas": 150,
                "temperature": 23.0,
                "humidity": 45.0,
                "distance_cm": 25.0,
                "is_closed": True,
                "timestamp": time.time()
            }

    def set_status_led(self, status):
        """status: 'NORMAL', 'WARNING', 'DANGER'"""
        if not self.has_hw:
            logger.debug(f"[가상 LED 제어] LED 상태를 {status}로 설정합니다.")
            return
            
        try:
            self.led_normal.off()
            self.led_warning.off()
            self.led_danger.off()
            
            if status == 'NORMAL':
                self.led_normal.on()
            elif status == 'WARNING':
                self.led_warning.on()
            elif status == 'DANGER':
                self.led_danger.on()
        except Exception as e:
            logger.error(f"[LED 제어 에러]: {e}")

    def run_ventilation(self):
        """환기 서보모터 구동 시연"""
        if not self.has_hw:
            logger.info("[가상 서보 모터] 🌀 환기 배출 댐퍼 개방 -> 1초 대기 -> 폐쇄")
            time.sleep(1)
            logger.info("[가상 서보 모터] 환기 완료.")
            return
            
        try:
            self.led_action.on()
            self.servo.max()
            time.sleep(1)
            self.servo.min()
            time.sleep(1)
            self.servo.detach() # 떨림 방지
            self.led_action.off()
        except Exception as e:
            logger.error(f"[서보모터 구동 에러]: {e}")


# 단독 테스트용 코드 (python src/hardware.py 로 실행 시)
if __name__ == "__main__":
    hw = HardwareController()
    try:
        while True:
            data = hw.get_sensor_data()
            print(f"센서 데이터: {data}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n종료합니다.")