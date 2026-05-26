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
        ★ 중요: 코랩에서 학습한 4개 특성(조도 제외) 순서를 엄격히 맞춥니다.
        """
        features = [
            raw_data["temperature"],  # 피처 1
            raw_data["humidity"],     # 피처 2
            raw_data["distance"],     # 피처 3
            raw_data["motion"]        # 피처 4
        ]
        # 텐서플로우 입력 규격인 2차원 배치 형태 (1, 4)의 float32 넘파이 배열로 생성
        return np.array([features], dtype=np.float32)

    def _postprocess(self, model_output, raw_data):
        """
        AI 모델 추론 결과는 텍스트(상태)로만 보여주고,
        하드웨어 제어는 순수하게 센서 원시값(raw_data)에 즉각 반응하도록 분리합니다.
        """
        # 1. 센서 원시값에 따른 1:1 즉각 하드웨어 제어 (돌봄 교감 반응)
        command = {
            "led_action": True if raw_data["motion"] == 1 else False,         # 움직임에 반응(감정 표현)
            "led_interact": True if raw_data["distance"] < 30.0 else False,   # 30cm 이내 접근 시 반응(스피커 교감)
            "led_sleep": True if raw_data["is_dark"] == 1 else False,         # 어두워지면 취침 모드 진입
            "led_care_status": True,                                          # 돌봄 시스템 가동 중
            "ai_status": "데이터 판독 불가 (AI 대기)"
        }
        
        # 2. AI 모델의 연산 결과는 대시보드 상태창(텍스트)용으로만 활용
        if model_output is not None:
            probabilities = model_output[0]
            predicted_class = int(np.argmax(probabilities))
            confidence = probabilities[predicted_class] * 100

            if predicted_class == 0:
                command["ai_status"] = f"정상 상태 (안정적, 신뢰도: {confidence:.1f}%)"
            elif predicted_class == 1:
                command["ai_status"] = f"활발한 교감 중 (사용자 활동, 신뢰도: {confidence:.1f}%)"
            elif predicted_class == 2:
                command["ai_status"] = f"위험 감지! (장시간 무반응/환경 이상, 신뢰도: {confidence:.1f}%)"
        else:
            # 모델 로드 실패 시 폴백
            command["ai_status"] = "돌봄 모니터링 중 (모델 오프라인)"
                
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
                
                # 3. 출력 텐서 채널에서 예측 완료된 결과 배열 복사
                output_tensor = self.interpreter.get_tensor(self.output_details[0]['index'])
            except Exception as e:
                logger.error(f"[추론 연산 에러] 임베디드 코어 연산 실패: {e}", exc_info=True)
                output_tensor = None
                
        # 전처리 -> 추론 -> 후처리를 거친 최종 제어 명령 사전을 백엔드로 반환
        decision = self._postprocess(output_tensor, raw_sensor_data)
        return decision
