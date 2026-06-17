import os
# os.environ["GPIOZERO_PIN_FACTORY"] = "pigpio"

from gpiozero import PWMOutputDevice

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
    import dht11
    import RPi.GPIO as GPIO
except ImportError:
    logger.warning("[하드웨어 알림] dht11 또는 RPi.GPIO 라이브러리가 없어 가상 DHT11 온습도 센서로 동작합니다.")
    HAS_HARDWARE = False

try:
    from gpiozero import DistanceSensor, Button, LED, MotionSensor, PWMOutputDevice
except ImportError:
    logger.warning("[하드웨어 알림] gpiozero 라이브러리가 없어 가상 GPIO 핀 및 액추에이터로 동작합니다.")
    HAS_HARDWARE = False


class HardwareController:
    def __init__(self):
        self.has_hw = HAS_HARDWARE
        self.servo_busy = False
        self.virtual_motion = False # 가상 PIR 트리거용 플래그
        
        if self.has_hw:
            try:
                # 1. 가스 센서 (MQ-6) - ADC 0번 채널 (A0)
                self.spi = spidev.SpiDev()
                self.spi.open(0, 0)
                self.spi.max_speed_hz = 1350000
                
                # 2. 온습도 센서 (DHT11) - GPIO 21
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                self.dht_sensor = dht11.DHT11(pin=21)
                
                # 3. 초음파 센서 (HC-SR04) - Trig: 17, Echo: 18
                self.ultrasonic = DistanceSensor(echo=18, trigger=17, max_distance=2.0)
                
                # 4. 리미트 스위치 (뚜껑 닫힘 감지) - GPIO 13
                self.limit_switch = Button(13, pull_up=True)
                
                # 5. 서보 모터 (강제 환기 또는 탈취제 분사) - GPIO 6
                # 50Hz (주기 20ms) 자체 PWM 출력 장치 설정
                self.servo = PWMOutputDevice(6, frequency=50)
                # 초깃값 약 94.5도(펄스폭 1.525ms -> duty_cycle = 1.525 / 20 = 0.07625, 리미트 스위치 접점 각도) 설정 후 떨림 방지를 위해 0.0 설정
                self.servo.value = 0.07625
                time.sleep(0.5)
                self.servo.value = 0.0
                
                # 6. 상태 표시 LED (19, 26, 16, 20)
                self.led_normal = LED(19)   # 초록 (정상)
                self.led_warning = LED(26)  # 노랑 (주의)
                self.led_danger = LED(16)   # 빨강 (위험)
                self.led_action = LED(20)   # 파랑 (팬/서보 작동 표시)
                
                # 7. PIR 센서 - GPIO 27
                self.pir = MotionSensor(27)
                self.pir.when_motion = self.on_motion_detected
            except Exception as e:
                logger.error(f"[하드웨어 초기화 실패] 에러: {e}. 가상 시뮬레이션 모드로 강제 전환합니다.")
                self.has_hw = False
        
        # 센서 데이터 일시 오독 방지용 Latch 변수 초기화
        self.last_gas = 120
        self.last_temperature = 24.0
        self.last_humidity = 50.0
        self.last_distance = 25.0

    def read_adc_channel(self, channel):
        """MCP3208(12bit) 특정 채널의 ADC 값 읽기"""
        adc = self.spi.xfer2([6 | (channel & 4) >> 2, (channel & 3) << 6, 0])
        data = ((adc[1] & 15) << 8) + adc[2]
        return data

    def read_gas(self):
        if not self.has_hw:
            # 가상 환경: 50 ~ 750 사이의 값 반환 (가상 변화 부여)
            return random.randint(100, 350)
            
        try:
            # A0, A1, A2 3개 채널의 가스 농도를 각각 계측
            gas_a0 = self.read_adc_channel(0)
            gas_a1 = self.read_adc_channel(1)
            gas_a2 = self.read_adc_channel(2)
            
            # 3개 채널의 가스 센서 평균값 산출
            avg_gas = int(round((gas_a0 + gas_a1 + gas_a2) / 3.0))
            return avg_gas
        except Exception as e:
            logger.error(f"[가스 센서 계측 에러] A0/A1/A2 다중 센서 읽기 실패: {e}")
            raise e

    def get_sensor_data(self):
        """모든 센서 데이터를 딕셔너리로 반환"""
        if not self.has_hw:
            # 가상 데이터 생성 (변동성 연출)
            gas = self.read_gas()
            temperature = round(random.uniform(22.0, 27.5), 1)
            humidity = round(random.uniform(40.0, 65.0), 1)
            distance = round(random.uniform(5.0, 28.0), 1)
            is_closed = True # 테스트 편의상 항상 닫힘 상태로 시뮬레이션
            
            # 가상 환경에서 무작위 또는 수동 트리거로 움직임 감시
            motion_detected = False
            if self.virtual_motion:
                motion_detected = True
            elif not self.servo_busy and random.random() < 0.05: # 약 5% 확률로 자동 트리거
                motion_detected = True
                self.virtual_motion = True
                import threading
                threading.Thread(target=self.run_pir_servo_sequence, daemon=True).start()
            
            return {
                "gas": gas,
                "temperature": temperature,
                "humidity": humidity,
                "distance_cm": distance,
                "is_closed": is_closed,
                "motion_detected": motion_detected or self.servo_busy,
                "timestamp": time.time()
            }
            
        # 각 센서별 개별 예외처리 및 Latching(이전 성공값 유지) 적용
        
        # 1. 가스 센서 계측
        try:
            gas = self.read_gas()
            self.last_gas = gas
        except Exception as e:
            logger.warning(f"[MQ-6 가스 센서 오류] 가스 값을 읽을 수 없습니다: {e}. 직전 유효값을 유지합니다.")
            gas = self.last_gas
            
        # 2. 온습도 센서 계측 (dht11 간헐적 오독 방지용 이전값 Latch 보정)
        try:
            result = self.dht_sensor.read()
            if result.is_valid():
                self.last_humidity = result.humidity
                self.last_temperature = result.temperature
        except Exception as e:
            logger.warning(f"[DHT11 온습도 센서 계측 오류] 온습도 센서 읽기 실패 ({e})")
        
        humidity = self.last_humidity
        temperature = self.last_temperature

        # 3. 초음파 거리 센서 계측 (DistanceSensorNoEcho 경고 방어 및 Latch)
        try:
            distance = self.ultrasonic.distance * 100
            self.last_distance = distance
        except Exception as e:
            logger.warning(f"[HC-SR04 초음파 센서 계측 오류] 거리 읽기 실패 ({e}). 직전 유효값을 유지합니다.")
            distance = self.last_distance

        # 4. 리미트 스위치 계측 (반대 로직 적용)
        try:
            # 반대 로직: switch가 눌리지 않았을 때(is_pressed=False)를 뚜껑이 닫힌 상태(is_closed=True)로 매핑
            is_closed = not self.limit_switch.is_pressed
        except Exception as e:
            logger.warning(f"[Limit Switch 오류] 스위치 상태를 읽을 수 없습니다: {e}")
            is_closed = True

        # 5. PIR 센서 계측
        try:
            motion_detected = self.pir.motion_detected
        except Exception as e:
            logger.warning(f"[PIR 센서 오류] 상태를 읽을 수 없습니다: {e}")
            motion_detected = False

        return {
            "gas": gas,
            "temperature": temperature,
            "humidity": humidity,
            "distance_cm": round(distance, 1),
            "is_closed": is_closed,
            "motion_detected": motion_detected or self.servo_busy,
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

    def on_motion_detected(self):
        logger.info("[PIR 센서] 움직임 감지됨! 서보모터 구동 시퀀스를 시작합니다.")
        import threading
        threading.Thread(target=self.run_pir_servo_sequence, daemon=True).start()

    def _set_servo_smooth(self, target_value, duration=0.6):
        """서보 모터 값을 부드럽게 조절하여 급격한 전류 소모 및 기어 충격을 방지합니다."""
        if not self.has_hw:
            return
            
        current_value = self.servo.value
        # PWM 신호가 차단(0.0)되어 있었던 경우, 기본 위치에서 시작하여 천천히 안착
        if current_value == 0.0:
            current_value = 0.07625
            self.servo.value = current_value
            time.sleep(0.05)
            
        step_time = 0.03
        steps = int(duration / step_time)
        if steps <= 0:
            self.servo.value = target_value
            return
            
        step_size = (target_value - current_value) / steps
        for _ in range(steps):
            current_value += step_size
            current_value = max(0.05, min(0.10, current_value))
            self.servo.value = current_value
            time.sleep(step_time)
            
        self.servo.value = target_value

    def run_pir_servo_sequence(self):
        if self.servo_busy:
            logger.info("[PIR 센서] 서보모터가 이미 구동 중이므로 추가 트리거를 무시합니다.")
            return
            
        self.servo_busy = True
        try:
            logger.info("[PIR 센서 서보 제어] 서보모터 회전: 원래 위치 -> 15도 (부드럽게 이동)")
            if self.has_hw:
                self.led_action.on()
                self._set_servo_smooth(0.054, duration=0.5)
            else:
                logger.info("[가상 서보 모터] 위치: 15도 이동")
                
            logger.info("[PIR 센서 서보 제어] 4초간 정지")
            time.sleep(4)
            
            logger.info("[PIR 센서 서보 제어] 서보모터 신호 차단: 무게에 의한 자연 복귀 유도")
            if self.has_hw:
                self.servo.value = 0.0   # 신호 차단 (모터 힘 해제)
                self.led_action.off()
            else:
                logger.info("[가상 서보 모터] 신호 차단 및 자연 복귀 시뮬레이션")
        except Exception as e:
            logger.error(f"[PIR 서보 제어 에러]: {e}")
        finally:
            self.servo_busy = False
            self.virtual_motion = False

    def run_ventilation(self):
        """환기 서보모터 구동 시연"""
        if not self.has_hw:
            logger.info("[가상 서보 모터] 🌀 환기 배출 댐퍼 개방 -> 1초 대기 -> 폐쇄")
            time.sleep(1)
            logger.info("[가상 서보 모터] 환기 완료.")
            return
            
        try:
            self.led_action.on()
            # 180도까지 부드럽게 개방
            self._set_servo_smooth(0.10, duration=0.8)
            time.sleep(0.5)
            # 15도까지 부드럽게 폐쇄
            self._set_servo_smooth(0.054, duration=0.8)
            time.sleep(0.5)
            self.servo.value = 0.0 # 떨림 방지 (신호 차단)
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