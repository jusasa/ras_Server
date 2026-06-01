# src/ai_engine.py
import numpy as np
import tflite_runtime.interpreter as tflite
import logging

logger = logging.getLogger(__name__)

class TFLiteEngine:
    def __init__(self, model_path="models/edge_model.tflite"):
        self.model_path = model_path
        self.is_loaded = False
        self.interpreter = None
        self._load_model()

    def _load_model(self):
        """실제 TFLite 모델 파일을 메모리에 로드하고 텐서를 할당합니다."""
        try:
            # 1. 텐서플로우 라이트 인터프리터 초기화
            self.interpreter = tflite.Interpreter(model_path=self.model_path)
            
            # 2. 런타임 메모리(텐서) 할당
            self.interpreter.allocate_tensors()
            
            # 3. 모델의 입력/출력 통로(Index) 정보 추출
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            logger.info("==================================================")
            logger.info("[AI 엔진 완료] 성공적으로 TFLite 모델을 로드했습니다.")
            logger.info(f" - 가동 모델: {self.model_path}")
            logger.info(f" - 입력 구조: {self.input_details[0]['shape']}") # [1, 4] 예측
            logger.info("==================================================")
            self.is_loaded = True
            
        except Exception as e:
            logger.error("==================================================")
            logger.error(f"[AI 엔진 에러] 실제 TFLite 모델 로드 중 실패했습니다.")
            logger.error(f" - 에러 내용: {e}", exc_info=True)
            logger.error(" - 안내: 모델이 없거나 손상되어 룰 기반 폴백 모드로 가동합니다.")
            logger.error("==================================================")
            self.is_loaded = False

    def _preprocess(self, raw_data):
        """
        센서 데이터를 모델 입력 규격에 맞게 전처리합니다.
        [gas, temperature, humidity, distance_cm] 4가지 피처를 추출합니다.
        """
        features = [
            raw_data.get("gas", 0.0),
            raw_data.get("temperature", 0.0),
            raw_data.get("humidity", 0.0),
            raw_data.get("distance_cm", 0.0)
        ]
        
        # 모델의 예상 배치 크기 확인 (예: ValueError Dimension mismatch 방어)
        expected_batch_size = 1
        if self.is_loaded and self.input_details is not None:
            try:
                expected_batch_size = self.input_details[0]['shape'][0]
            except Exception:
                expected_batch_size = 1

        # 배치 차원 팽창 (예: [1, 4] -> [expected_batch_size, 4])
        input_data = np.repeat(np.array([features], dtype=np.float32), expected_batch_size, axis=0)
        return input_data

    def _postprocess(self, model_output, raw_data):
        """
        AI 모델 추론 결과를 분석하여 Smart Eco-Bin의 상태와 제어 명령을 결정합니다.
        """
        # 기본 제어 명령 구조 (정상 상태 디폴트)
        command = {
            "status": "NORMAL",        # 'NORMAL', 'WARNING', 'DANGER'
            "led_action": False,       # LED 4 (팬/서보 작동 표시) 켬 여부
            "run_fan": False,          # 환기 서보모터 구동 필요 여부
            "ai_status": "데이터 판독 불가 (AI 대기)"
        }
        
        # 1. AI 모델의 연산 결과는 대시보드 상태창(텍스트) 및 하드웨어 제어 결정에 활용
        if model_output is not None:
            output_array = np.array(model_output)
            
            # Case 1: 출력 노드가 여러 개여서 확률 분포인 경우 (예: [1, 3] 또는 [3])
            if output_array.size > 1:
                probabilities = output_array[0] if output_array.ndim > 1 else output_array
                predicted_class = int(np.argmax(probabilities))
                confidence = float(probabilities[predicted_class] * 100)
                confidence_str = f" (신뢰도: {confidence:.1f}%)"
            # Case 2: 출력 노드가 1개여서 클래스 라벨이 직접 출력되는 경우
            else:
                val = float(output_array.flat[0])
                predicted_class = max(0, min(2, int(round(val))))
                confidence_str = ""

            if predicted_class == 0:
                command["status"] = "NORMAL"
                command["led_action"] = False
                command["run_fan"] = False
                command["ai_status"] = f"정상 상태{confidence_str}"
            elif predicted_class == 1:
                command["status"] = "WARNING"
                command["led_action"] = False
                command["run_fan"] = False
                command["ai_status"] = f"주의 상태 (부패 위험 가능성){confidence_str}"
            elif predicted_class == 2:
                command["status"] = "DANGER"
                command["led_action"] = True
                command["run_fan"] = True
                command["ai_status"] = f"위험 감지! (부패 및 악취 위험 차단 가동){confidence_str}"
        else:
            # 모델 로드 실패 시 룰 기반 폴백 분류 및 상태 라벨링
            gas = raw_data.get("gas", 0.0)
            temp = raw_data.get("temperature", 24.0)
            dist = raw_data.get("distance_cm", 50.0)

            # 1) 위험 상태 (가스 농도가 임계값 이상이거나 온도가 매우 높거나 쓰레기 적재거리가 매우 가까울 때)
            if gas >= 600.0 or temp >= 33.0 or dist <= 10.0:
                command["status"] = "DANGER"
                command["led_action"] = True
                command["run_fan"] = True
                command["ai_status"] = "위험 감지! (센서 임계치 초과 [폴백 룰])"
            # 2) 주의 상태
            elif gas >= 300.0 or temp >= 28.0 or dist <= 25.0:
                command["status"] = "WARNING"
                command["led_action"] = False
                command["run_fan"] = False
                command["ai_status"] = "주의 상태 (악취 및 부패 우려 [폴백 룰])"
            # 3) 정상/안정 상태
            else:
                command["status"] = "NORMAL"
                command["led_action"] = False
                command["run_fan"] = False
                command["ai_status"] = "정상 상태 (안정적 [폴백 룰])"
                
        return command

    def predict(self, raw_sensor_data):
        """main.py 백엔드 룹에서 주기적으로 호출하는 실시간 AI 추론 API"""
        input_tensor = self._preprocess(raw_sensor_data)
        output_tensor = None
        
        # 인터프리터가 정상 가동 중일 때만 진짜 하드웨어 가속 추론 전개
        if self.is_loaded and self.interpreter is not None:
            try:
                # 1. 입력 텐서 채널에 전처리된 센서 배열 주입
                self.interpreter.set_tensor(self.input_details[0]['index'], input_tensor)
                
                # 2. 하드웨어 런타임 추론 구동 (Invoke)
                self.interpreter.invoke()
                
                # 3. 출력 텐서 채널에서 예측 완료된 결과 배열 복사 (배치 크기만큼 출력됨)
                raw_output = self.interpreter.get_tensor(self.output_details[0]['index'])
                
                # 첫 번째 샘플에 대한 추론만 슬라이싱하여 반환 (후처리와 호환성 유지)
                output_tensor = raw_output[0:1]
            except Exception as e:
                logger.error(f"[추론 연산 에러] 임베디드 코어 연산 실패: {e}", exc_info=True)
                output_tensor = None
                
        # 전처리 -> 추론 -> 후처리를 거친 최종 제어 명령 사전을 백엔드로 반환
        decision = self._postprocess(output_tensor, raw_sensor_data)
        return decision
