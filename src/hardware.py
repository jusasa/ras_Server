import time
import spidev
import Adafruit_DHT
from gpiozero import DistanceSensor, Button, Servo, LED

class HardwareController:
    def __init__(self):
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

    def read_gas(self):
        # MCP3208(12bit) 기준 A0 채널 읽기
        adc = self.spi.xfer2([6 | (0 & 4) >> 2, (0 & 3) << 6, 0])
        data = ((adc[1] & 15) << 8) + adc[2]
        return data

    def get_sensor_data(self):
        """모든 센서 데이터를 딕셔너리로 반환"""
        gas = self.read_gas()
        humidity, temperature = Adafruit_DHT.read_retry(self.dht_sensor, self.dht_pin)
        distance = self.ultrasonic.distance * 100 # cm 단위 변환
        is_closed = self.limit_switch.is_pressed # True면 닫힘, False면 열림
        
        # DHT11은 가끔 에러로 None을 뱉으므로 예외 처리
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

    def set_status_led(self, status):
        """status: 'NORMAL', 'WARNING', 'DANGER'"""
        self.led_normal.off()
        self.led_warning.off()
        self.led_danger.off()
        
        if status == 'NORMAL':
            self.led_normal.on()
        elif status == 'WARNING':
            self.led_warning.on()
        elif status == 'DANGER':
            self.led_danger.on()

    def run_ventilation(self):
        """환기 서보모터 구동 테스트"""
        self.led_action.on()
        self.servo.max()
        time.sleep(1)
        self.servo.min()
        time.sleep(1)
        self.servo.detach() # 떨림 방지
        self.led_action.off()

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