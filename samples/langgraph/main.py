"""
LangGraph 여행 일정 생성기
==========================

이 샘플이 보여주는 것:
- 에이전트의 사고 흐름이 명시적인 State/Node로 나뉘어 있다
- 실행 순서가 "그래프"로 고정되어 있다
- 조건 분기가 그래프 엣지로 표현된다

철학: "LangGraph는 에이전트를 즉흥적인 LLM 호출이 아니라
       설계 가능한 프로그램으로 만들려는 시도다."
"""

from typing import TypedDict, Literal, List, Dict, Any
from dataclasses import dataclass
import json

# ============================================================
# MOCK DATA - LLM 호출 대신 사용할 정적 데이터
# ============================================================

BUSAN_PLACES = {
    "cafe": [
        {"name": "모모스커피", "area": "전포동", "vibe": "조용함", "solo_friendly": True},
        {"name": "블랙업커피", "area": "전포동", "vibe": "조용함", "solo_friendly": True},
        {"name": "테라로사", "area": "해운대", "vibe": "넓음", "solo_friendly": True},
    ],
    "exhibition": [
        {"name": "부산시립미술관", "area": "해운대", "duration": 120, "solo_friendly": True},
        {"name": "F1963", "area": "수영", "duration": 90, "solo_friendly": True},
        {"name": "뮤지엄원", "area": "해운대", "duration": 60, "solo_friendly": True},
    ],
    "restaurant": [
        {"name": "본전돼지국밥", "area": "서면", "type": "혼밥가능", "solo_friendly": True},
        {"name": "밀양순대국", "area": "부전동", "type": "혼밥가능", "solo_friendly": True},
        {"name": "원조할매국밥", "area": "서면", "type": "혼밥가능", "solo_friendly": True},
    ],
}

AREA_DISTANCES = {
    ("전포동", "수영"): 10,
    ("전포동", "해운대"): 25,
    ("수영", "해운대"): 15,
    ("서면", "전포동"): 5,
    ("서면", "수영"): 15,
    ("부전동", "전포동"): 3,
}

def get_distance(area1: str, area2: str) -> int:
    """두 지역 간 이동 시간(분) 반환"""
    if area1 == area2:
        return 0
    key = (area1, area2) if (area1, area2) in AREA_DISTANCES else (area2, area1)
    return AREA_DISTANCES.get(key, 20)


# ============================================================
# STATE 정의 - 그래프를 통과하는 데이터 구조
# ============================================================

class TravelState(TypedDict):
    """
    LangGraph의 핵심: 상태(State)가 그래프 노드를 통과하며 변환된다.
    각 노드는 이 상태를 읽고, 수정된 부분만 반환한다.
    """
    # 입력
    raw_request: str

    # 파싱된 요청
    duration: str  # "1박 2일"
    travel_style: str  # "혼자"
    preferences: List[str]  # ["조용한 카페", "전시"]
    constraints: List[str]  # ["혼밥 가능", "이동 동선 최소화"]

    # 분석 결과
    place_types_needed: List[str]
    priority: str  # "minimize_travel" | "maximize_variety"

    # 선택된 장소들
    selected_places: List[Dict[str, Any]]

    # 일정
    day1_schedule: List[Dict[str, Any]]
    day2_schedule: List[Dict[str, Any]]

    # 최종 출력
    final_output: str

    # 실행 로그 (철학을 보여주기 위해)
    execution_log: List[str]


# ============================================================
# 노드(Node) 함수들 - 각각 하나의 처리 단계
# ============================================================

def parse_request(state: TravelState) -> dict:
    """
    [Node 1] 사용자 요청을 구조화된 데이터로 파싱

    이 노드의 역할: 자연어 → 구조화된 데이터
    실제 시스템에서는 LLM이 이 작업을 수행
    """
    log = ["=" * 60]
    log.append("[Node: parse_request] 사용자 요청 파싱 중...")
    log.append(f"  입력: {state['raw_request'][:50]}...")

    # Mock 파싱 결과
    parsed = {
        "duration": "1박 2일",
        "travel_style": "혼자",
        "preferences": ["조용한 카페", "전시"],
        "constraints": ["혼밥 가능", "이동 동선 최소화"],
    }

    log.append(f"  파싱 결과: {json.dumps(parsed, ensure_ascii=False, indent=4)}")

    return {
        **parsed,
        "execution_log": state.get("execution_log", []) + log
    }


def analyze_preferences(state: TravelState) -> dict:
    """
    [Node 2] 선호도 분석 및 장소 유형 결정

    이 노드의 역할: 선호도 → 필요한 장소 유형 + 우선순위
    """
    log = ["=" * 60]
    log.append("[Node: analyze_preferences] 선호도 분석 중...")

    place_types = []
    if "조용한 카페" in state["preferences"]:
        place_types.append("cafe")
        log.append("  → '조용한 카페' 선호 → cafe 유형 필요")
    if "전시" in state["preferences"]:
        place_types.append("exhibition")
        log.append("  → '전시' 선호 → exhibition 유형 필요")

    # 식사는 기본 추가
    place_types.append("restaurant")
    log.append("  → 식사 장소 기본 추가 → restaurant 유형 필요")

    # 우선순위 결정
    priority = "minimize_travel" if "이동 동선 최소화" in state["constraints"] else "maximize_variety"
    log.append(f"  → 제약조건 분석 결과 우선순위: {priority}")

    return {
        "place_types_needed": place_types,
        "priority": priority,
        "execution_log": state.get("execution_log", []) + log
    }


def select_places_minimize_travel(state: TravelState) -> dict:
    """
    [Node 3a] 이동 최소화 전략으로 장소 선택

    조건부 분기: priority가 "minimize_travel"일 때 이 노드로 라우팅
    """
    log = ["=" * 60]
    log.append("[Node: select_places_minimize_travel] 이동 최소화 전략으로 장소 선택...")
    log.append("  전략: 같은 지역 내 장소들을 우선 선택")

    selected = []
    target_area = "전포동"  # 이동 최소화를 위해 중심 지역 선택
    log.append(f"  기준 지역: {target_area}")

    for place_type in state["place_types_needed"]:
        candidates = BUSAN_PLACES.get(place_type, [])
        # 같은 지역 우선, 없으면 가까운 지역
        sorted_candidates = sorted(
            candidates,
            key=lambda p: get_distance(target_area, p["area"])
        )
        if sorted_candidates:
            place = sorted_candidates[0]
            selected.append({**place, "type": place_type})
            log.append(f"  선택: {place['name']} ({place['area']}) - {place_type}")

    # 1박 2일이므로 추가 장소 선택
    for place_type in ["cafe", "exhibition"]:
        candidates = [p for p in BUSAN_PLACES.get(place_type, [])
                     if {**p, "type": place_type} not in selected]
        sorted_candidates = sorted(
            candidates,
            key=lambda p: get_distance(target_area, p["area"])
        )
        if sorted_candidates:
            place = sorted_candidates[0]
            selected.append({**place, "type": place_type})
            log.append(f"  추가 선택: {place['name']} ({place['area']}) - {place_type}")

    return {
        "selected_places": selected,
        "execution_log": state.get("execution_log", []) + log
    }


def select_places_maximize_variety(state: TravelState) -> dict:
    """
    [Node 3b] 다양성 극대화 전략으로 장소 선택

    조건부 분기: priority가 "maximize_variety"일 때 이 노드로 라우팅
    """
    log = ["=" * 60]
    log.append("[Node: select_places_maximize_variety] 다양성 극대화 전략으로 장소 선택...")
    log.append("  전략: 다양한 지역의 장소들을 선택")

    selected = []
    used_areas = set()

    for place_type in state["place_types_needed"]:
        candidates = BUSAN_PLACES.get(place_type, [])
        # 사용하지 않은 지역 우선
        sorted_candidates = sorted(
            candidates,
            key=lambda p: (p["area"] in used_areas, p["name"])
        )
        if sorted_candidates:
            place = sorted_candidates[0]
            selected.append({**place, "type": place_type})
            used_areas.add(place["area"])
            log.append(f"  선택: {place['name']} ({place['area']}) - {place_type}")

    return {
        "selected_places": selected,
        "execution_log": state.get("execution_log", []) + log
    }


def generate_schedule(state: TravelState) -> dict:
    """
    [Node 4] 선택된 장소들로 일정 생성

    이 노드의 역할: 장소 목록 → 시간 순서가 있는 일정
    """
    log = ["=" * 60]
    log.append("[Node: generate_schedule] 일정 생성 중...")

    places = state["selected_places"]

    # Day 1: 카페 → 전시 → 저녁
    day1 = []
    cafes = [p for p in places if p["type"] == "cafe"]
    exhibitions = [p for p in places if p["type"] == "exhibition"]
    restaurants = [p for p in places if p["type"] == "restaurant"]

    if cafes:
        day1.append({
            "time": "10:00",
            "place": cafes[0],
            "reason": "여행 시작을 조용한 카페에서 여유롭게"
        })
        log.append(f"  Day1 10:00 - {cafes[0]['name']}")

    if exhibitions:
        day1.append({
            "time": "14:00",
            "place": exhibitions[0],
            "reason": "오후 시간 전시 관람으로 문화 충전"
        })
        log.append(f"  Day1 14:00 - {exhibitions[0]['name']}")

    if restaurants:
        day1.append({
            "time": "18:00",
            "place": restaurants[0],
            "reason": "현지 맛집에서 혼밥으로 하루 마무리"
        })
        log.append(f"  Day1 18:00 - {restaurants[0]['name']}")

    # Day 2: 나머지 장소들
    day2 = []
    remaining_cafes = cafes[1:] if len(cafes) > 1 else []
    remaining_exhibitions = exhibitions[1:] if len(exhibitions) > 1 else []

    if remaining_cafes:
        day2.append({
            "time": "09:00",
            "place": remaining_cafes[0],
            "reason": "아침 커피와 함께 여유로운 시작"
        })
        log.append(f"  Day2 09:00 - {remaining_cafes[0]['name']}")

    if remaining_exhibitions:
        day2.append({
            "time": "11:00",
            "place": remaining_exhibitions[0],
            "reason": "체크아웃 후 가볍게 둘러보기"
        })
        log.append(f"  Day2 11:00 - {remaining_exhibitions[0]['name']}")
    elif exhibitions:
        # 남은 전시가 없으면 다른 활동 제안
        day2.append({
            "time": "11:00",
            "place": {"name": "광안리 산책", "area": "광안리"},
            "reason": "체크아웃 후 바다 산책으로 여행 마무리"
        })
        log.append(f"  Day2 11:00 - 광안리 산책")

    return {
        "day1_schedule": day1,
        "day2_schedule": day2,
        "execution_log": state.get("execution_log", []) + log
    }


def format_output(state: TravelState) -> dict:
    """
    [Node 5] 최종 출력 포맷팅

    이 노드의 역할: 구조화된 일정 → 사람이 읽기 좋은 텍스트
    """
    log = ["=" * 60]
    log.append("[Node: format_output] 최종 출력 생성 중...")

    output_lines = []
    output_lines.append("=" * 60)
    output_lines.append("🗓️  부산 1박 2일 여행 일정")
    output_lines.append("=" * 60)
    output_lines.append("")

    # Day 1
    output_lines.append("📍 Day 1")
    output_lines.append("-" * 40)
    for item in state["day1_schedule"]:
        place = item["place"]
        output_lines.append(f"  {item['time']} | {place['name']}")
        output_lines.append(f"           📍 {place.get('area', '')}")
        output_lines.append(f"           💭 {item['reason']}")
        output_lines.append("")

    # Day 2
    output_lines.append("📍 Day 2")
    output_lines.append("-" * 40)
    for item in state["day2_schedule"]:
        place = item["place"]
        output_lines.append(f"  {item['time']} | {place['name']}")
        output_lines.append(f"           📍 {place.get('area', '')}")
        output_lines.append(f"           💭 {item['reason']}")
        output_lines.append("")

    # 일정 구성 이유
    output_lines.append("=" * 60)
    output_lines.append("📝 전체 구성 이유")
    output_lines.append("-" * 40)
    output_lines.append("• 혼자 여행에 적합한 장소들로 구성")
    output_lines.append("• 조용한 카페와 전시 공간 위주")
    output_lines.append(f"• 이동 동선 최소화를 위해 {state['priority']} 전략 적용")
    output_lines.append("• 혼밥 가능한 식당 선정")
    output_lines.append("=" * 60)

    final_output = "\n".join(output_lines)
    log.append("  출력 생성 완료")

    return {
        "final_output": final_output,
        "execution_log": state.get("execution_log", []) + log
    }


# ============================================================
# 조건부 라우팅 함수
# ============================================================

def route_by_priority(state: TravelState) -> Literal["minimize", "variety"]:
    """
    그래프의 조건부 분기를 담당하는 라우터

    이것이 LangGraph의 핵심: 상태를 기반으로 다음 노드를 결정
    """
    if state["priority"] == "minimize_travel":
        return "minimize"
    else:
        return "variety"


# ============================================================
# 그래프 구성 - 이것이 LangGraph의 핵심!
# ============================================================

# LangGraph 패키지 사용 가능 여부 확인
try:
    from langgraph.graph import StateGraph, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    print("Note: langgraph 패키지가 설치되지 않아 Mock 모드로 실행합니다.")
    print("      철학을 보여주는 데모로 동작합니다.\n")


class MockCompiledGraph:
    """
    LangGraph가 설치되지 않은 환경에서 철학을 보여주기 위한 Mock 클래스

    이 클래스는 LangGraph의 invoke() 패턴을 시뮬레이션합니다:
    - 상태가 노드를 통과하며 변환된다
    - 조건부 분기가 그래프로 표현된다
    """

    def __init__(self, nodes, edges, conditional_edges, entry_point):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point

    def invoke(self, initial_state: TravelState) -> TravelState:
        """그래프 실행 시뮬레이션"""
        state = dict(initial_state)
        current_node = self.entry_point

        while current_node:
            # 노드 실행
            if current_node in self.nodes:
                result = self.nodes[current_node](state)
                state.update(result)

            # 다음 노드 결정
            if current_node in self.conditional_edges:
                router_func, route_map = self.conditional_edges[current_node]
                route_key = router_func(state)
                current_node = route_map.get(route_key)
            elif current_node in self.edges:
                current_node = self.edges[current_node]
            else:
                current_node = None

        return state


def build_travel_graph():
    """
    StateGraph를 구성하고 반환

    이 함수를 보면 LangGraph의 철학이 드러난다:
    - 실행 흐름이 "코드"가 아니라 "그래프"로 정의된다
    - 각 단계가 명시적인 노드로 분리된다
    - 조건부 분기도 그래프의 일부로 선언된다
    """
    if LANGGRAPH_AVAILABLE:
        # 실제 LangGraph 사용
        graph = StateGraph(TravelState)

        # 노드 추가 - 각각이 하나의 처리 단계
        graph.add_node("parse_request", parse_request)
        graph.add_node("analyze_preferences", analyze_preferences)
        graph.add_node("select_places_minimize", select_places_minimize_travel)
        graph.add_node("select_places_variety", select_places_maximize_variety)
        graph.add_node("generate_schedule", generate_schedule)
        graph.add_node("format_output", format_output)

        # 엣지 추가 - 실행 순서 정의
        graph.add_edge(START, "parse_request")
        graph.add_edge("parse_request", "analyze_preferences")

        # 조건부 분기 - 이것이 그래프의 강점!
        graph.add_conditional_edges(
            "analyze_preferences",
            route_by_priority,
            {
                "minimize": "select_places_minimize",
                "variety": "select_places_variety"
            }
        )

        # 분기 후 합류
        graph.add_edge("select_places_minimize", "generate_schedule")
        graph.add_edge("select_places_variety", "generate_schedule")
        graph.add_edge("generate_schedule", "format_output")
        graph.add_edge("format_output", END)

        return graph.compile()
    else:
        # Mock 버전 - 철학을 보여주기 위한 시뮬레이션
        nodes = {
            "parse_request": parse_request,
            "analyze_preferences": analyze_preferences,
            "select_places_minimize": select_places_minimize_travel,
            "select_places_variety": select_places_maximize_variety,
            "generate_schedule": generate_schedule,
            "format_output": format_output,
        }

        edges = {
            "parse_request": "analyze_preferences",
            "select_places_minimize": "generate_schedule",
            "select_places_variety": "generate_schedule",
            "generate_schedule": "format_output",
            "format_output": None,  # END
        }

        conditional_edges = {
            "analyze_preferences": (route_by_priority, {
                "minimize": "select_places_minimize",
                "variety": "select_places_variety"
            })
        }

        return MockCompiledGraph(nodes, edges, conditional_edges, "parse_request")


# ============================================================
# 실행
# ============================================================

def main():
    print("=" * 60)
    print("LangGraph 여행 일정 생성기")
    print("=" * 60)
    print()
    print("이 샘플이 보여주는 것:")
    print("  - 에이전트의 사고 흐름이 명시적인 State/Node로 나뉘어 있다")
    print("  - 실행 순서가 '그래프'로 고정되어 있다")
    print("  - 조건 분기가 그래프 엣지로 표현된다")
    print()

    # 그래프 구성
    app = build_travel_graph()

    # 입력
    user_request = """부산 1박 2일 여행
- 혼자 여행
- 조용한 카페, 전시 위주
- 혼밥 가능
- 이동 동선 최소화"""

    print("📝 사용자 요청:")
    print("-" * 40)
    print(user_request)
    print()

    # 그래프 실행
    print("🔄 그래프 실행 로그:")
    print("-" * 40)

    initial_state: TravelState = {
        "raw_request": user_request,
        "duration": "",
        "travel_style": "",
        "preferences": [],
        "constraints": [],
        "place_types_needed": [],
        "priority": "",
        "selected_places": [],
        "day1_schedule": [],
        "day2_schedule": [],
        "final_output": "",
        "execution_log": []
    }

    # invoke로 전체 그래프 실행
    final_state = app.invoke(initial_state)

    # 실행 로그 출력
    for log_line in final_state["execution_log"]:
        print(log_line)

    print()
    print("🎯 최종 결과:")
    print(final_state["final_output"])


if __name__ == "__main__":
    main()
