"""
AgentScope 여행 일정 생성기
===========================

이 샘플이 보여주는 것:
- 에이전트 간 상호작용이 메시지 단위로 이루어진다
- 실행 구조가 '스크립트'라기보다 작은 '시스템'처럼 보인다
- 누가 누구에게 어떤 메시지를 보냈는지가 흐름으로 드러난다

철학: "AgentScope는 에이전트를 운영 가능한 실행 단위로 다루려는 접근이다."

Note: 이 샘플은 AgentScope의 철학을 보여주기 위해 실제 LLM 호출 없이
      Mock 응답을 사용합니다. 핵심은 메시지 기반 통신 패턴입니다.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import json
import uuid


# ============================================================
# 메시지 시스템 - AgentScope의 핵심!
# ============================================================

@dataclass
class Msg:
    """
    AgentScope의 핵심: 모든 에이전트 간 통신은 Msg 객체로 이루어진다.

    특징:
    - 명시적인 송신자(name)와 역할(role)
    - 구조화된 content (문자열 또는 dict)
    - 추적 가능한 메타데이터 (id, timestamp)
    - 라우팅을 위한 to 필드
    """
    name: str           # 송신 에이전트 이름
    content: Any        # 메시지 내용 (문자열 또는 구조화된 데이터)
    role: str           # "user", "assistant", "system"
    to: Optional[str] = None  # 수신 에이전트 이름 (None이면 브로드캐스트)

    # 메타데이터 - 운영 관점에서 중요
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def get_text_content(self) -> str:
        """content를 문자열로 반환"""
        if isinstance(self.content, str):
            return self.content
        return json.dumps(self.content, ensure_ascii=False, indent=2)

    def __str__(self) -> str:
        to_str = f" → {self.to}" if self.to else " → [ALL]"
        return f"[{self.timestamp}] [{self.id}] {self.name}{to_str}\n{self._format_content()}"

    def _format_content(self) -> str:
        content_str = self.get_text_content()
        lines = content_str.split('\n')
        return '\n'.join(f"  │ {line}" for line in lines)


# ============================================================
# 메시지 버스 - 에이전트 간 통신 인프라
# ============================================================

class MessageBus:
    """
    에이전트 간 메시지를 라우팅하는 중앙 버스

    AgentScope의 운영적 특성을 보여주는 핵심 컴포넌트:
    - 모든 메시지가 이 버스를 통과한다
    - 메시지 로깅 및 추적이 가능하다
    - 브로드캐스트 및 직접 전달을 지원한다
    """

    def __init__(self, debug: bool = True):
        self.messages: List[Msg] = []
        self.agents: Dict[str, 'BaseAgent'] = {}
        self.debug = debug

    def register(self, agent: 'BaseAgent'):
        """에이전트를 버스에 등록"""
        self.agents[agent.name] = agent
        if self.debug:
            print(f"  📡 Agent registered: {agent.name}")

    def send(self, msg: Msg, already_printed: bool = False) -> List[Msg]:
        """
        메시지 전송 및 응답 수집

        운영 관점: 모든 메시지 흐름이 추적 가능하다
        """
        # 이미 저장된 메시지인지 확인
        if msg not in self.messages:
            self.messages.append(msg)

        # 이미 출력된 메시지가 아닌 경우에만 출력
        if self.debug and not already_printed:
            print(f"\n{'─' * 60}")
            print(msg)

        responses = []

        if msg.to:
            # 특정 에이전트에게 직접 전달
            if msg.to in self.agents:
                response = self.agents[msg.to].receive(msg)
                if response:
                    responses.append(response)
                    self.messages.append(response)
                    if self.debug:
                        print(f"\n{'─' * 60}")
                        print(response)
        else:
            # 브로드캐스트 (송신자 제외)
            for name, agent in self.agents.items():
                if name != msg.name:
                    response = agent.receive(msg)
                    if response:
                        responses.append(response)
                        self.messages.append(response)
                        if self.debug:
                            print(f"\n{'─' * 60}")
                            print(response)

        return responses


# ============================================================
# 베이스 에이전트 - 운영 가능한 실행 단위
# ============================================================

class BaseAgent:
    """
    AgentScope 에이전트의 기본 클래스

    특징:
    - 독립적인 실행 단위로 설계됨
    - 메시지를 받고(receive) 처리 결과를 반환
    - 상태(memory)를 가질 수 있음
    - 다른 에이전트와 결합 없이 독립 동작 가능
    """

    def __init__(self, name: str, system_prompt: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self.memory: List[Msg] = []  # 이 에이전트가 받은 메시지 기록

    def receive(self, msg: Msg) -> Optional[Msg]:
        """
        메시지를 받아 처리하고 응답을 반환

        이 메서드가 AgentScope 에이전트의 핵심 인터페이스다.
        """
        self.memory.append(msg)
        return self._process(msg)

    def _process(self, msg: Msg) -> Optional[Msg]:
        """서브클래스에서 구현할 처리 로직"""
        raise NotImplementedError


# ============================================================
# 구체적인 에이전트들
# ============================================================

class CoordinatorAgent(BaseAgent):
    """
    Coordinator: 전체 흐름을 조율하는 에이전트

    역할:
    - 사용자 요청을 받아 분해한다
    - 다른 에이전트들에게 작업을 할당한다
    - 최종 결과를 조합한다
    """

    def __init__(self):
        super().__init__(
            name="Coordinator",
            system_prompt="여행 일정 생성을 조율하는 에이전트"
        )
        self.state = "idle"  # idle, collecting, finalizing

    def _process(self, msg: Msg) -> Optional[Msg]:
        if msg.role == "user":
            # 사용자 요청 → 작업 분배
            self.state = "collecting"
            return Msg(
                name=self.name,
                role="assistant",
                to="PlaceExpert",
                content={
                    "action": "request_places",
                    "requirements": {
                        "destination": "부산",
                        "duration": "1박 2일",
                        "style": "혼자 여행",
                        "preferences": ["조용한 카페", "전시"],
                        "constraints": ["혼밥 가능", "이동 동선 최소화"]
                    },
                    "instruction": "요구사항에 맞는 장소들을 추천해주세요"
                }
            )
        elif msg.name == "PlaceExpert":
            # 장소 전문가 응답 → 일정 전문가에게 전달
            return Msg(
                name=self.name,
                role="assistant",
                to="ScheduleExpert",
                content={
                    "action": "create_schedule",
                    "places": msg.content.get("places", []),
                    "duration": "1박 2일",
                    "instruction": "이 장소들로 1박 2일 일정을 만들어주세요"
                }
            )
        elif msg.name == "ScheduleExpert":
            # 일정 전문가 응답 → 최종 결과 생성
            self.state = "finalizing"
            return Msg(
                name=self.name,
                role="assistant",
                to=None,  # 브로드캐스트
                content={
                    "action": "final_result",
                    "schedule": msg.content.get("schedule", {}),
                    "summary": "일정 생성이 완료되었습니다"
                }
            )
        return None


class PlaceExpertAgent(BaseAgent):
    """
    PlaceExpert: 장소 추천 전문 에이전트

    역할:
    - 요구사항에 맞는 장소를 추천한다
    - 각 장소에 대한 상세 정보를 제공한다
    """

    # Mock 장소 데이터
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

    def __init__(self):
        super().__init__(
            name="PlaceExpert",
            system_prompt="부산 지역 장소 전문가"
        )

    def _process(self, msg: Msg) -> Optional[Msg]:
        if isinstance(msg.content, dict) and msg.content.get("action") == "request_places":
            # 장소 추천 요청 처리
            requirements = msg.content.get("requirements", {})
            preferences = requirements.get("preferences", [])

            recommended = []

            # 선호도에 따른 장소 선택
            if "조용한 카페" in preferences:
                recommended.extend(self.PLACES["cafe"])
            if "전시" in preferences:
                recommended.extend(self.PLACES["exhibition"])

            # 식사 장소 추가
            recommended.extend(self.PLACES["restaurant"])

            return Msg(
                name=self.name,
                role="assistant",
                to="Coordinator",
                content={
                    "action": "places_response",
                    "places": recommended,
                    "reasoning": "혼자 여행에 적합하고 조용한 장소들을 선정했습니다"
                }
            )
        return None


class ScheduleExpertAgent(BaseAgent):
    """
    ScheduleExpert: 일정 구성 전문 에이전트

    역할:
    - 장소들을 시간순으로 배치한다
    - 동선을 최적화한다
    - 각 일정에 이유를 부여한다
    """

    def __init__(self):
        super().__init__(
            name="ScheduleExpert",
            system_prompt="여행 일정 구성 전문가"
        )

    def _process(self, msg: Msg) -> Optional[Msg]:
        if isinstance(msg.content, dict) and msg.content.get("action") == "create_schedule":
            places = msg.content.get("places", [])

            # 동선 최적화를 고려한 일정 구성
            schedule = {
                "day1": {
                    "theme": "전포동/수영 권역",
                    "items": [
                        {
                            "time": "10:00",
                            "place": "모모스커피",
                            "area": "전포동",
                            "reason": "조용한 카페에서 여행 시작"
                        },
                        {
                            "time": "14:00",
                            "place": "F1963",
                            "area": "수영",
                            "reason": "전시 관람 및 복합문화공간 탐방"
                        },
                        {
                            "time": "18:00",
                            "place": "밀양순대국",
                            "area": "부전동",
                            "reason": "현지 맛집에서 혼밥"
                        }
                    ]
                },
                "day2": {
                    "theme": "해운대 권역",
                    "items": [
                        {
                            "time": "09:00",
                            "place": "테라로사",
                            "area": "해운대",
                            "reason": "바다 근처 카페에서 여유로운 아침"
                        },
                        {
                            "time": "11:00",
                            "place": "해운대 해변 산책",
                            "area": "해운대",
                            "reason": "체크아웃 후 가벼운 마무리"
                        }
                    ]
                },
                "optimization_notes": [
                    "권역별 분리로 이동 시간 최소화",
                    "혼자 여행에 적합한 장소만 선정",
                    "여유로운 시간 배분"
                ]
            }

            return Msg(
                name=self.name,
                role="assistant",
                to="Coordinator",
                content={
                    "action": "schedule_response",
                    "schedule": schedule,
                    "total_places": len(places)
                }
            )
        return None


# ============================================================
# 시스템 실행 - 메시지 기반 오케스트레이션
# ============================================================

class TravelPlanningSystem:
    """
    여행 일정 생성 시스템

    AgentScope의 핵심 개념:
    - 에이전트들은 독립적인 실행 단위다
    - 시스템은 메시지 버스를 통해 에이전트들을 연결한다
    - 모든 상호작용이 명시적인 메시지로 추적 가능하다
    """

    def __init__(self):
        print("=" * 60)
        print("🔧 시스템 초기화")
        print("=" * 60)

        # 메시지 버스 생성
        self.bus = MessageBus(debug=True)

        # 에이전트 생성 및 등록
        self.coordinator = CoordinatorAgent()
        self.place_expert = PlaceExpertAgent()
        self.schedule_expert = ScheduleExpertAgent()

        self.bus.register(self.coordinator)
        self.bus.register(self.place_expert)
        self.bus.register(self.schedule_expert)

        print()

    def run(self, user_request: str) -> str:
        """
        시스템 실행

        흐름:
        1. 사용자 메시지 → Coordinator
        2. Coordinator → PlaceExpert (장소 요청)
        3. PlaceExpert → Coordinator (장소 응답)
        4. Coordinator → ScheduleExpert (일정 요청)
        5. ScheduleExpert → Coordinator (일정 응답)
        6. Coordinator → 최종 결과 브로드캐스트
        """
        print("=" * 60)
        print("📨 메시지 흐름 시작")
        print("=" * 60)

        # Step 1: 사용자 요청 메시지 생성
        user_msg = Msg(
            name="User",
            role="user",
            to="Coordinator",
            content=user_request
        )

        # Step 2: Coordinator가 처리 시작
        responses = self.bus.send(user_msg)

        # Step 3-6: 연쇄적인 메시지 전달
        while responses:
            next_responses = []
            for response in responses:
                if response.to:  # 특정 에이전트에게 전달
                    # response는 이미 출력됨, already_printed=True
                    new_responses = self.bus.send(response, already_printed=True)
                    next_responses.extend(new_responses)
            responses = next_responses

        # 최종 결과 포맷팅
        print("\n" + "=" * 60)
        print("📋 최종 결과")
        print("=" * 60)

        final_output = self._format_final_output()
        print(final_output)

        return final_output

    def _format_final_output(self) -> str:
        """마지막 메시지에서 일정 추출 및 포맷팅"""

        # 마지막 Coordinator 메시지 찾기
        for msg in reversed(self.bus.messages):
            if msg.name == "Coordinator" and isinstance(msg.content, dict):
                if msg.content.get("action") == "final_result":
                    schedule = msg.content.get("schedule", {})
                    return self._format_schedule(schedule)

        return "일정 생성 실패"

    def _format_schedule(self, schedule: dict) -> str:
        lines = []
        lines.append("")
        lines.append("━" * 50)
        lines.append("🗓️  부산 1박 2일 여행 일정")
        lines.append("━" * 50)

        for day_key in ["day1", "day2"]:
            if day_key in schedule:
                day = schedule[day_key]
                day_num = "Day 1" if day_key == "day1" else "Day 2"
                lines.append("")
                lines.append(f"📍 {day_num} ({day.get('theme', '')})")
                lines.append("─" * 50)

                for item in day.get("items", []):
                    lines.append(f"  {item['time']} | {item['place']}")
                    lines.append(f"           📍 {item['area']}")
                    lines.append(f"           💭 {item['reason']}")

        lines.append("")
        lines.append("━" * 50)
        lines.append("📝 구성 이유")
        lines.append("─" * 50)
        for note in schedule.get("optimization_notes", []):
            lines.append(f"  • {note}")
        lines.append("━" * 50)

        return "\n".join(lines)


# ============================================================
# 실행
# ============================================================

def main():
    print("=" * 60)
    print("AgentScope 여행 일정 생성기")
    print("=" * 60)
    print()
    print("이 샘플이 보여주는 것:")
    print("  - 에이전트 간 상호작용이 메시지 단위로 이루어진다")
    print("  - 실행 구조가 '스크립트'가 아닌 '시스템'처럼 동작한다")
    print("  - 누가 누구에게 어떤 메시지를 보냈는지 추적 가능하다")
    print()
    print("에이전트 구성:")
    print("  - Coordinator: 흐름 조율")
    print("  - PlaceExpert: 장소 추천")
    print("  - ScheduleExpert: 일정 구성")
    print()

    user_request = """부산 1박 2일 여행
- 혼자 여행
- 조용한 카페, 전시 위주
- 혼밥 가능
- 이동 동선 최소화"""

    system = TravelPlanningSystem()
    result = system.run(user_request)


if __name__ == "__main__":
    main()
