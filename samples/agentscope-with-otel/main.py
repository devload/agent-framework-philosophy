"""
AgentScope + OpenTelemetry: 관찰 가능한 에이전트 시스템
========================================================

이 샘플이 보여주는 것:
- OpenTelemetry + Jaeger (무료 오픈소스)만으로 완전한 모니터링이 가능하다
- 설정 몇 줄로 에이전트 시스템의 모든 흐름이 시각화된다
- 병목, 에러, 의존관계가 Jaeger UI에서 즉시 확인된다

실행 방법:
  1. Jaeger 실행: docker run -d -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest
  2. 샘플 실행: python main.py
  3. Jaeger UI 확인: http://localhost:16686

철학: "에이전트를 시스템으로 실행하는 순간, 관찰은 기능이 아니라 조건이 된다."
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import contextmanager
import json
import uuid
import time
import random
import sys

# ============================================================
# OpenTelemetry 설정 - Jaeger 연동
# ============================================================

OTEL_AVAILABLE = False

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace import Status, StatusCode

    # OTLP Exporter (Jaeger, Tempo, 등 모든 OTLP 호환 백엔드와 연동)
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    OTEL_AVAILABLE = True

except ImportError as e:
    print("=" * 70)
    print("❌ OpenTelemetry가 설치되지 않았습니다.")
    print("=" * 70)
    print()
    print("이 샘플은 OTel + Jaeger로 무료 모니터링을 보여주는 것이 목적입니다.")
    print("다음 명령으로 설치하세요:")
    print()
    print("  pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
    print()
    sys.exit(1)


def setup_tracing(service_name: str = "travel-planning-agents",
                  jaeger_endpoint: str = "http://localhost:4317"):
    """
    OpenTelemetry 트레이싱 설정

    이 함수 하나로 Jaeger 연동이 완료된다.
    무료 오픈소스만으로 프로덕션 레벨 관찰이 가능해진다.
    """
    # 서비스 리소스 정의
    resource = Resource.create({
        SERVICE_NAME: service_name,
        "service.version": "1.0.0",
        "deployment.environment": "demo"
    })

    # Tracer Provider 생성
    provider = TracerProvider(resource=resource)

    # OTLP Exporter 설정 (Jaeger로 전송)
    otlp_exporter = OTLPSpanExporter(
        endpoint=jaeger_endpoint,
        insecure=True  # 로컬 개발용
    )

    # BatchSpanProcessor로 효율적인 전송
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # 글로벌 Tracer Provider 설정
    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)


# ============================================================
# 메시지 시스템 (AgentScope 원본 유지)
# ============================================================

@dataclass
class Msg:
    """메시지 객체"""
    name: str
    content: Any
    role: str
    to: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S.%f")[:-3])

    def get_text_content(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return json.dumps(self.content, ensure_ascii=False, indent=2)

    def __str__(self) -> str:
        to_str = f" → {self.to}" if self.to else " → [ALL]"
        return f"[{self.timestamp}] [{self.id}] {self.name}{to_str}"


# ============================================================
# 계측된 메시지 버스 - OTel Span 자동 생성
# ============================================================

class TracedMessageBus:
    """
    OpenTelemetry로 계측된 메시지 버스

    모든 메시지 전송이 자동으로 Span으로 기록되어
    Jaeger UI에서 시각화된다.
    """

    def __init__(self, tracer, debug: bool = True):
        self.tracer = tracer
        self.messages: List[Msg] = []
        self.agents: Dict[str, 'TracedAgent'] = {}
        self.debug = debug

    def register(self, agent: 'TracedAgent'):
        self.agents[agent.name] = agent
        if self.debug:
            print(f"  📡 Agent registered: {agent.name}")

    def send(self, msg: Msg, already_printed: bool = False) -> List[Msg]:
        """메시지 전송 - 자동으로 Span 생성"""

        if msg not in self.messages:
            self.messages.append(msg)

        # 이미 출력된 메시지는 다시 출력하지 않음
        if self.debug and not already_printed:
            print(f"\n{'─' * 60}")
            print(msg)

        responses = []
        target = msg.to if msg.to else "broadcast"

        # 메시지 전송을 Span으로 기록
        with self.tracer.start_as_current_span(
            f"message: {msg.name} → {target}",
            attributes={
                "message.id": msg.id,
                "message.from": msg.name,
                "message.to": target,
                "message.role": msg.role,
            }
        ) as span:
            if msg.to:
                if msg.to in self.agents:
                    response = self.agents[msg.to].receive(msg, self.tracer)
                    if response:
                        responses.append(response)
                        self.messages.append(response)
                        if self.debug:
                            print(f"\n{'─' * 60}")
                            print(response)
            else:
                for name, agent in self.agents.items():
                    if name != msg.name:
                        response = agent.receive(msg, self.tracer)
                        if response:
                            responses.append(response)
                            self.messages.append(response)
                            if self.debug:
                                print(f"\n{'─' * 60}")
                                print(response)

        return responses


# ============================================================
# 계측된 에이전트
# ============================================================

class TracedAgent:
    """OpenTelemetry로 계측된 에이전트"""

    def __init__(self, name: str, system_prompt: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self.memory: List[Msg] = []

    def receive(self, msg: Msg, tracer) -> Optional[Msg]:
        self.memory.append(msg)

        # 에이전트 처리를 Span으로 기록
        with tracer.start_as_current_span(
            f"agent.{self.name}.process",
            attributes={
                "agent.name": self.name,
                "agent.type": self.__class__.__name__,
                "input.message_id": msg.id,
            }
        ) as span:
            try:
                result = self._process(msg, tracer)
                if result:
                    span.set_attribute("output.message_id", result.id)
                return result
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    def _process(self, msg: Msg, tracer) -> Optional[Msg]:
        raise NotImplementedError


# ============================================================
# 구체적인 에이전트들
# ============================================================

class CoordinatorAgent(TracedAgent):
    """Coordinator: 전체 흐름 조율"""

    def __init__(self):
        super().__init__(name="Coordinator", system_prompt="여행 일정 생성을 조율하는 에이전트")

    def _process(self, msg: Msg, tracer) -> Optional[Msg]:
        if msg.role == "user":
            return Msg(
                name=self.name, role="assistant", to="PlaceExpert",
                content={
                    "action": "request_places",
                    "requirements": {
                        "destination": "부산", "duration": "1박 2일",
                        "style": "혼자 여행",
                        "preferences": ["조용한 카페", "전시"],
                        "constraints": ["혼밥 가능", "이동 동선 최소화"]
                    }
                }
            )
        elif msg.name == "PlaceExpert":
            return Msg(
                name=self.name, role="assistant", to="ScheduleExpert",
                content={
                    "action": "create_schedule",
                    "places": msg.content.get("places", []),
                    "duration": "1박 2일"
                }
            )
        elif msg.name == "ScheduleExpert":
            return Msg(
                name=self.name, role="assistant", to=None,
                content={
                    "action": "final_result",
                    "schedule": msg.content.get("schedule", {}),
                    "summary": "일정 생성이 완료되었습니다"
                }
            )
        return None


class PlaceExpertAgent(TracedAgent):
    """
    PlaceExpert: 장소 추천

    ⚠️ 의도적 지연: 외부 DB 조회를 시뮬레이션
    → Jaeger에서 이 병목이 명확히 보인다
    """

    PLACES = {
        "cafe": [
            {"name": "모모스커피", "area": "전포동", "features": ["조용함", "혼자 작업 좋음"]},
            {"name": "테라로사", "area": "해운대", "features": ["넓음", "바다 근처"]},
        ],
        "exhibition": [
            {"name": "F1963", "area": "수영", "features": ["복합문화공간", "전시+서점"]},
            {"name": "부산시립미술관", "area": "해운대", "features": ["무료", "기획전시"]},
        ],
        "restaurant": [
            {"name": "밀양순대국", "area": "부전동", "features": ["혼밥 가능", "현지 맛집"]},
        ]
    }

    def __init__(self, simulate_delay: bool = True):
        super().__init__(name="PlaceExpert", system_prompt="부산 지역 장소 전문가")
        self.simulate_delay = simulate_delay

    def _process(self, msg: Msg, tracer) -> Optional[Msg]:
        if isinstance(msg.content, dict) and msg.content.get("action") == "request_places":

            # 외부 DB 조회 시뮬레이션 - Jaeger에서 이 Span이 병목으로 보임
            if self.simulate_delay:
                with tracer.start_as_current_span(
                    "external.place_database.query",
                    attributes={
                        "db.system": "postgresql",
                        "db.name": "places",
                        "db.operation": "SELECT",
                        "db.statement": "SELECT * FROM places WHERE city = 'busan'"
                    }
                ) as db_span:
                    delay = random.uniform(0.8, 1.2)  # 800ms ~ 1200ms
                    time.sleep(delay)
                    db_span.set_attribute("db.rows_affected", 5)

            requirements = msg.content.get("requirements", {})
            preferences = requirements.get("preferences", [])
            recommended = []

            if "조용한 카페" in preferences:
                recommended.extend(self.PLACES["cafe"])
            if "전시" in preferences:
                recommended.extend(self.PLACES["exhibition"])
            recommended.extend(self.PLACES["restaurant"])

            return Msg(
                name=self.name, role="assistant", to="Coordinator",
                content={"action": "places_response", "places": recommended}
            )
        return None


class ScheduleExpertAgent(TracedAgent):
    """
    ScheduleExpert: 일정 구성

    ⚠️ 조건부 실패: 일정 최적화 실패 시뮬레이션
    → Jaeger에서 에러 trace가 빨간색으로 표시됨
    """

    def __init__(self, failure_rate: float = 0.0):
        super().__init__(name="ScheduleExpert", system_prompt="여행 일정 구성 전문가")
        self.failure_rate = failure_rate

    def _process(self, msg: Msg, tracer) -> Optional[Msg]:
        if isinstance(msg.content, dict) and msg.content.get("action") == "create_schedule":

            # 일정 최적화 작업
            with tracer.start_as_current_span(
                "optimization.route_calculation",
                attributes={"algorithm": "tsp_greedy"}
            ) as opt_span:
                time.sleep(0.1)  # 최적화 시간

                # 조건부 실패
                if random.random() < self.failure_rate:
                    raise Exception("Route optimization failed: timeout after 30s")

                opt_span.set_attribute("optimization.iterations", 42)

            places = msg.content.get("places", [])
            schedule = {
                "day1": {
                    "theme": "전포동/수영 권역",
                    "items": [
                        {"time": "10:00", "place": "모모스커피", "area": "전포동", "reason": "조용한 카페에서 여행 시작"},
                        {"time": "14:00", "place": "F1963", "area": "수영", "reason": "전시 관람 및 복합문화공간 탐방"},
                        {"time": "18:00", "place": "밀양순대국", "area": "부전동", "reason": "현지 맛집에서 혼밥"}
                    ]
                },
                "day2": {
                    "theme": "해운대 권역",
                    "items": [
                        {"time": "09:00", "place": "테라로사", "area": "해운대", "reason": "바다 근처 카페에서 여유로운 아침"},
                        {"time": "11:00", "place": "해운대 해변 산책", "area": "해운대", "reason": "체크아웃 후 가벼운 마무리"}
                    ]
                },
                "optimization_notes": ["권역별 분리로 이동 시간 최소화", "혼자 여행에 적합한 장소만 선정"]
            }

            return Msg(
                name=self.name, role="assistant", to="Coordinator",
                content={"action": "schedule_response", "schedule": schedule, "total_places": len(places)}
            )
        return None


# ============================================================
# 관찰 가능한 여행 계획 시스템
# ============================================================

class ObservableTravelPlanningSystem:
    """
    OpenTelemetry + Jaeger로 완전히 관찰 가능한 시스템

    모든 요청이 Jaeger UI에서:
    - 전체 흐름 시각화
    - 각 단계별 소요 시간
    - 에러 발생 지점
    - 서비스 간 의존관계
    로 확인 가능하다.
    """

    def __init__(self, tracer, simulate_delay: bool = True, failure_rate: float = 0.0):
        print("=" * 60)
        print("🔧 관찰 가능한 시스템 초기화")
        print("=" * 60)

        self.tracer = tracer
        self.bus = TracedMessageBus(tracer, debug=True)

        self.coordinator = CoordinatorAgent()
        self.place_expert = PlaceExpertAgent(simulate_delay=simulate_delay)
        self.schedule_expert = ScheduleExpertAgent(failure_rate=failure_rate)

        self.bus.register(self.coordinator)
        self.bus.register(self.place_expert)
        self.bus.register(self.schedule_expert)

        print()

    def run(self, user_request: str) -> str:
        """
        시스템 실행

        전체 요청이 하나의 Root Span으로 묶여
        Jaeger에서 완전한 Trace로 시각화된다.
        """

        # Root Span: 전체 요청을 하나의 Trace로
        with self.tracer.start_as_current_span(
            "travel_planning.request",
            attributes={
                "request.type": "travel_planning",
                "request.destination": "부산",
                "request.duration": "1박2일",
                "user.type": "solo_traveler"
            }
        ) as root_span:

            print("=" * 60)
            print("📨 메시지 흐름 시작")
            print("=" * 60)

            user_msg = Msg(name="User", role="user", to="Coordinator", content=user_request)
            responses = self.bus.send(user_msg)

            while responses:
                next_responses = []
                for response in responses:
                    if response.to:
                        # response는 이미 출력됨
                        new_responses = self.bus.send(response, already_printed=True)
                        next_responses.extend(new_responses)
                responses = next_responses

            print("\n" + "=" * 60)
            print("📋 최종 결과")
            print("=" * 60)

            final_output = self._format_final_output()
            print(final_output)

            # Trace에 결과 요약 추가
            root_span.set_attribute("result.success", True)
            root_span.set_attribute("result.total_messages", len(self.bus.messages))

            return final_output

    def _format_final_output(self) -> str:
        for msg in reversed(self.bus.messages):
            if msg.name == "Coordinator" and isinstance(msg.content, dict):
                if msg.content.get("action") == "final_result":
                    schedule = msg.content.get("schedule", {})
                    return self._format_schedule(schedule)
        return "일정 생성 실패"

    def _format_schedule(self, schedule: dict) -> str:
        lines = ["", "━" * 50, "🗓️  부산 1박 2일 여행 일정", "━" * 50]

        for day_key in ["day1", "day2"]:
            if day_key in schedule:
                day = schedule[day_key]
                day_num = "Day 1" if day_key == "day1" else "Day 2"
                lines.extend(["", f"📍 {day_num} ({day.get('theme', '')})", "─" * 50])

                for item in day.get("items", []):
                    lines.append(f"  {item['time']} | {item['place']}")
                    lines.append(f"           📍 {item['area']}")
                    lines.append(f"           💭 {item['reason']}")

        lines.extend(["", "━" * 50])
        return "\n".join(lines)


# ============================================================
# 실행
# ============================================================

def main():
    print("=" * 70)
    print("AgentScope + OpenTelemetry + Jaeger")
    print("무료 오픈소스만으로 에이전트 시스템 모니터링하기")
    print("=" * 70)
    print()

    # Jaeger 실행 확인 안내
    print("📋 사전 준비:")
    print("─" * 70)
    print("Jaeger가 실행 중이어야 합니다. 다음 명령으로 실행하세요:")
    print()
    print("  docker run -d --name jaeger \\")
    print("    -p 16686:16686 \\")
    print("    -p 4317:4317 \\")
    print("    jaegertracing/all-in-one:latest")
    print()
    print("─" * 70)
    print()

    input("Jaeger가 실행 중이면 Enter를 눌러 계속...")
    print()

    # OpenTelemetry 설정 - 이 한 줄로 Jaeger 연동 완료
    print("🔌 OpenTelemetry 초기화 중...")
    tracer = setup_tracing(
        service_name="travel-planning-agents",
        jaeger_endpoint="http://localhost:4317"
    )
    print("✅ Jaeger 연동 완료")
    print()

    user_request = """부산 1박 2일 여행
- 혼자 여행
- 조용한 카페, 전시 위주
- 혼밥 가능
- 이동 동선 최소화"""

    # 시스템 실행
    system = ObservableTravelPlanningSystem(
        tracer=tracer,
        simulate_delay=True,  # DB 조회 지연 시뮬레이션
        failure_rate=0.0      # 실패율 (0.3 = 30% 확률로 실패)
    )

    result = system.run(user_request)

    # Jaeger UI 안내
    print()
    print("=" * 70)
    print("🎯 Jaeger에서 Trace 확인하기")
    print("=" * 70)
    print()
    print("1. 브라우저에서 열기: http://localhost:16686")
    print()
    print("2. Service 선택: 'travel-planning-agents'")
    print()
    print("3. 'Find Traces' 클릭")
    print()
    print("4. Trace를 클릭하면:")
    print("   - 전체 요청 흐름이 시각화됨")
    print("   - 각 Span의 소요 시간이 표시됨")
    print("   - 'external.place_database.query'에서 병목 확인 가능")
    print("   - 에러 발생 시 빨간색으로 표시됨")
    print()
    print("=" * 70)
    print()
    print("💡 이것이 무료 오픈소스(OTel + Jaeger)만으로 가능합니다!")
    print()


if __name__ == "__main__":
    main()
