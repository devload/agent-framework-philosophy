# 흐름 → 협업 → 시스템 → 관찰: 에이전트가 시스템이 되기까지

> **LangGraph, AutoGen, AgentScope, OpenTelemetry로 보는 에이전트 프레임워크의 철학적 진화**

📖 **[Medium 글 보기](https://medium.com/@sunghyunroh/%ED%9D%90%EB%A6%84-%ED%98%91%EC%97%85-%EC%8B%9C%EC%8A%A4%ED%85%9C-%EA%B4%80%EC%B0%B0-%EC%97%90%EC%9D%B4%EC%A0%84%ED%8A%B8%EA%B0%80-%EC%8B%9C%EC%8A%A4%ED%85%9C%EC%9D%B4-%EB%90%98%EA%B8%B0%EA%B9%8C%EC%A7%80-d8bebd24fbd6)**

이 저장소는 에이전트 프레임워크의 **철학적 진화**를 보여주기 위한 샘플 프로젝트입니다.
기능 비교가 아닌, **사고 방식의 진화**를 직관적으로 느낄 수 있도록 구성했습니다.

---

## 4단계 진화 요약

```
1️⃣ LangGraph    → "이 흐름을 어떻게 정의할 것인가?"
2️⃣ AutoGen     → "이 문제를 누가 어떻게 같이 풀 것인가?"
3️⃣ AgentScope  → "이걸 어떻게 시스템으로 실행할 것인가?"
4️⃣ + OTel      → "이 시스템을 우리는 어떻게 이해하고 설명할 것인가?"
```

---

## 공통 문제: 부산 1박 2일 여행 일정 생성기

모든 샘플은 동일한 입력을 받습니다:

```
부산 1박 2일 여행
- 혼자 여행
- 조용한 카페, 전시 위주
- 혼밥 가능
- 이동 동선 최소화
```

**결과는 비슷하지만, 과정과 구조는 명확히 다릅니다.**

---

## 실행 방법

```bash
# 1️⃣ LangGraph 샘플
cd samples/langgraph
pip install langgraph  # 또는 Mock 모드로 실행 가능
python main.py

# 2️⃣ AutoGen 샘플 (외부 의존성 없음)
cd samples/autogen
python main.py

# 3️⃣ AgentScope 샘플 (외부 의존성 없음)
cd samples/agentscope
python main.py

# 4️⃣ AgentScope + OpenTelemetry + Jaeger 샘플
# 먼저 Jaeger 실행
docker run -d --name jaeger -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest

cd samples/agentscope-with-otel
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
python main.py

# Jaeger UI에서 확인: http://localhost:16686
```

> Note: 모든 샘플은 LLM API 호출 없이 Mock 데이터로 동작합니다.

---

## 각 단계가 보여주는 것

### 1️⃣ LangGraph: "설계 가능한 프로그램"

```
samples/langgraph/
```

**핵심 철학:**
> "에이전트를 즉흥적인 LLM 호출이 아니라, **설계 가능한 프로그램**으로 만들려는 시도"

**코드에서 느껴지는 것:**
- `StateGraph`로 전체 흐름을 **그래프로 선언**
- 각 노드가 **명시적인 단계**
- 조건 분기가 **그래프 엣지로 표현**

**실행 로그 예시:**
```
[Node: parse_request] 사용자 요청 파싱 중...
[Node: analyze_preferences] 선호도 분석 중...
[Node: select_places_minimize_travel] 이동 최소화 전략으로 장소 선택...
[Node: generate_schedule] 일정 생성 중...
[Node: format_output] 최종 출력 생성 중...
```

---

### 2️⃣ AutoGen: "사람 팀처럼 협업"

```
samples/autogen/
```

**핵심 철학:**
> "에이전트를 **사람 팀처럼 협업**시키려는 프레임워크"

**코드에서 느껴지는 것:**
- 역할 기반 에이전트: `Planner`, `LocalGuide`, `Editor`
- **대화를 통해 결과를 다듬어감**
- **수정/보완/합의**의 과정이 드러남

**실행 로그 예시:**
```
[Turn 1] Planner:
  부산 1박 2일 혼자 여행 일정 초안을 작성했습니다...

[Turn 2] LocalGuide:
  안녕하세요, 부산 현지 정보를 공유드립니다...

[Turn 3] Planner:
  LocalGuide님의 추천을 반영하여 일정을 수정했습니다...

[Turn 4] Editor:
  최종 검토 완료했습니다. ✅ 검토 결과: 승인
```

---

### 3️⃣ AgentScope: "운영 가능한 실행 단위"

```
samples/agentscope/
```

**핵심 철학:**
> "에이전트를 **운영 가능한 실행 단위**로 다루려는 접근"

**코드에서 느껴지는 것:**
- 모든 통신이 **`Msg` 객체**로 이루어짐
- **누가 누구에게** 어떤 메시지를 보냈는지 명시적
- `MessageBus`가 중앙에서 메시지를 라우팅
- 메시지 ID, 타임스탬프로 **추적 가능**

**실행 로그 예시:**
```
[10:30:01] [a1b2c3d4] User → Coordinator
  │ 부산 1박 2일 여행...

[10:30:01] [e5f6g7h8] Coordinator → PlaceExpert
  │ {"action": "request_places", "requirements": {...}}

[10:30:01] [i9j0k1l2] PlaceExpert → Coordinator
  │ {"action": "places_response", "places": [...]}
```

---

### 4️⃣ AgentScope + OpenTelemetry + Jaeger: "무료로 완전한 모니터링"

```
samples/agentscope-with-otel/
```

**핵심 철학:**
> "**무료 오픈소스(OTel + Jaeger)만으로** 에이전트 시스템의 완전한 모니터링이 가능하다."

**실행 방법:**
```bash
# 1. Jaeger 실행 (Docker 한 줄)
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest

# 2. 의존성 설치
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

# 3. 샘플 실행
python main.py

# 4. Jaeger UI에서 Trace 확인
open http://localhost:16686
```

**Jaeger UI에서 보이는 것:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ travel_planning.request                                    1.24s    │
├─────────────────────────────────────────────────────────────────────┤
│ ├─ message: User → Coordinator                             2ms      │
│ │  └─ agent.Coordinator.process                            1ms      │
│ ├─ message: Coordinator → PlaceExpert                      1.1s     │
│ │  └─ agent.PlaceExpert.process                            1.08s    │
│ │     └─ external.place_database.query  ← ⚠️ 병목!         1.05s    │
│ ├─ message: Coordinator → ScheduleExpert                   120ms    │
│ │  └─ agent.ScheduleExpert.process                         110ms    │
│ │     └─ optimization.route_calculation                    100ms    │
│ └─ message: Coordinator → broadcast                        5ms      │
└─────────────────────────────────────────────────────────────────────┘
```

**Jaeger가 자동으로 보여주는 것:**
- **Trace Timeline**: 전체 요청 흐름이 시각화됨
- **Span Duration**: 각 작업의 소요 시간
- **병목 식별**: 긴 span이 한눈에 보임
- **에러 추적**: 실패한 span이 빨간색으로 표시
- **서비스 맵**: 에이전트 간 의존관계

**왜 AgentScope만으로는 부족해졌는가?**

AgentScope의 메시지 로그는 "무엇이 일어났는지"를 보여준다.
하지만 다음 질문에는 답할 수 없다:
- "왜 느렸는가?" → 지연 시간이 로그에 없다
- "어디서 시간이 걸렸는가?" → 전체 흐름의 계층 구조가 없다
- "에러의 원인은 무엇인가?" → 에러 전파 경로가 보이지 않는다

**OTel + Jaeger가 들어오면서 무엇이 가능해졌는가?**

| 질문 | AgentScope만 | + OTel + Jaeger |
|------|--------------|-----------------|
| 무엇이 일어났는가? | ✅ 로그 | ✅ + 시각화 |
| 얼마나 걸렸는가? | ❌ 불가 | ✅ Timeline |
| 어디서 느렸는가? | ❌ 불가 | ✅ 병목 하이라이트 |
| 왜 실패했는가? | ❌ 불가 | ✅ 에러 span 추적 |
| 서비스 의존관계? | ❌ 불가 | ✅ Service Map |

**이 모든 것이 무료 오픈소스로 가능하다!**

---

## 철학의 4단계 진화

| 단계 | 프레임워크 | 핵심 질문 | 해결하는 문제 |
|------|------------|-----------|---------------|
| 1️⃣ | LangGraph | 흐름을 어떻게 정의할까? | LLM 출력 불안정 |
| 2️⃣ | AutoGen | 누가 어떻게 협업할까? | 단일 관점 한계 |
| 3️⃣ | AgentScope | 어떻게 시스템으로 실행할까? | 운영 환경 대응 |
| 4️⃣ | + OTel | 이걸 어떻게 이해할까? | 복잡성 관찰 |

---

## 왜 이런 순서로 등장했는가?

### 1단계: LangGraph (2023~)
> "LLM 출력을 예측 가능하게 만들자"

- 문제: LLM의 출력이 불안정함
- 해결: 실행 흐름을 **그래프로 명시**하여 제어

### 2단계: AutoGen (2023~)
> "복잡한 문제는 여러 관점이 필요하다"

- 문제: 단일 에이전트로는 복잡한 문제 해결 어려움
- 해결: **역할 분담**과 **대화**로 품질 향상

### 3단계: AgentScope (2024~)
> "에이전트를 운영 환경에서 돌리자"

- 문제: 프로토타입은 되는데 운영이 어려움
- 해결: **메시지 기반** 아키텍처로 추적/확장 용이

### 4단계: + OpenTelemetry (필연)
> "시스템이 되면, 관찰이 필요해진다"

- 문제: 시스템은 돌아가는데 **왜 느린지, 왜 실패했는지 모름**
- 해결: **분산 트레이싱**으로 전체 흐름 관찰

```
┌─────────────────────────────────────────────────────────────┐
│  "에이전트를 시스템으로 실행하는 순간,                      │
│   관찰은 기능이 아니라 조건이 된다."                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 어떤 조합을 선택할까?

| 상황 | 추천 |
|------|------|
| 실행 흐름을 정확히 제어하고 싶다 | **LangGraph** |
| 복잡한 문제를 여러 전문가가 협업해서 풀고 싶다 | **AutoGen** |
| 에이전트를 운영 환경에서 돌리고 싶다 | **AgentScope** |
| 운영 중인 에이전트 시스템을 이해하고 싶다 | **AgentScope + OTel** |

---

## 디렉토리 구조

```
samples/
├── langgraph/              # 1️⃣ 설계 가능한 프로그램
│   ├── main.py
│   └── requirements.txt
├── autogen/                # 2️⃣ 팀처럼 협업
│   ├── main.py
│   └── requirements.txt
├── agentscope/             # 3️⃣ 시스템으로 실행
│   ├── main.py
│   └── requirements.txt
├── agentscope-with-otel/   # 4️⃣ 관찰 가능한 시스템
│   ├── main.py
│   └── requirements.txt
└── README.md
```

---

## 참고 자료

- [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/)
- [AutoGen 공식 문서](https://microsoft.github.io/autogen/)
- [AgentScope GitHub](https://github.com/agentscope-ai/agentscope)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
