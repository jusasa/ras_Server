import RPi.GPIO as GPIO
import dht11
import time

class HardwareController:
    def __init__(self):
        # 핀 번호 체계를 BCM으로 통일 및 경고 비활성화
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        
        # 1. 액추에이터 (LED) 핀 번호
        self.led_motion = 16
        self.led_dist = 20
        self.led_dark = 19
        self.led_status = 26
        
        # 초기값을 무조건 LOW로 동시 할당하여 튕김 방지
        for pin in [self.led_motion, self.led_dist, self.led_dark, self.led_status]:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        
        # 2. 일반 센서 (PIR) 핀 설정 - 조도(CdS) 완전히 삭제됨
        self.pir_pin = 21  
        GPIO.setup(self.pir_pin, GPIO.IN)
        
        # 3. 온습도 센서 (DHT11) 핀 설정
        self.dht_pin = 12  
        self.dht = dht11.DHT11(pin=self.dht_pin)
        
        # 4. 초음파 센서 핀 설정
        self.trig_pin = 5  
        self.echo_pin = 6  
        GPIO.setup(self.trig_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.echo_pin, GPIO.IN)
        
        # 온습도 캐싱 변수
        self.last_temp = 0.0
        self.last_hum = 0.0

    def _get_distance_safe(self, timeout=0.04):
        """초음파 센서 무한 대기를 방어하는 안전한 거리 측정 함수"""
        GPIO.output(self.trig_pin, True)
        time.sleep(0.00001)
        GPIO.output(self.trig_pin, False)

        pulse_start = time.time()
        timeout_start = pulse_start

        while GPIO.input(self.echo_pin) == 0:
            pulse_start = time.time()
            if pulse_start - timeout_start > timeout:
                return 200.0

        pulse_end = time.time()
        timeout_start = pulse_end

        while GPIO.input(self.echo_pin) == 1:
            pulse_end = time.time()
            if pulse_end - timeout_start > timeout:
                return 200.0

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        
        if distance > 200.0:
            return 200.0
            
        return round(distance, 1)

    def read_sensors(self):
        """모든 센서 데이터를 읽어 딕셔너리로 반환"""
        # 1. 온습도 읽기
        dht_result = self.dht.read()
        if dht_result.is_valid():
            self.last_temp = dht_result.temperature
            self.last_hum = dht_result.humidity

        # 2. 초음파 거리 측정
        distance = self._get_distance_safe()

        # 3. PIR 모션 읽기
        motion = GPIO.input(self.pir_pin)

        # 4. 조도 읽기 (물리 센서를 뺐으므로 항상 0 반환하도록 하드코딩)
        is_dark = 0

        return {
            "temperature": self.last_temp,
            "humidity": self.last_hum,
            "distance": distance,
            "motion": motion,
            "is_dark": is_dark
        }

    def control_leds(self, control_dict):
        """AI 추론 결과에 따른 LED 제어"""
        GPIO.output(self.led_motion, GPIO.HIGH if control_dict.get("led_motion") else GPIO.LOW)
        GPIO.output(self.led_dist, GPIO.HIGH if control_dict.get("led_dist") else GPIO.LOW)
        GPIO.output(self.led_dark, GPIO.HIGH if control_dict.get("led_dark") else GPIO.LOW)
        GPIO.output(self.led_status, GPIO.HIGH if control_dict.get("led_status") else GPIO.LOW)
        
    def cleanup(self):
        """종료 시 자원 해제"""
        for pin in [self.led_motion, self.led_dist, self.led_dark, self.led_status]:
            GPIO.output(pin, GPIO.LOW)
        GPIO.cleanup()
