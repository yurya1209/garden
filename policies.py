"""

이 파일의 함수들을 수정하여 프로젝트를 완성하세요.
시뮬레이션 인프라(이벤트 콜백, AMR 예약, 설비 상태 머신 등)는
core/scheduling.py 에 있으며 해당 파일을 수정을 해야 한다면, 꼭 수정한 부분과 이유를 주석으로 명확히 언급해주세요.

──────────────────────────────────────────────────────────────
과업 ↔ 함수 매핑
──────────────────────────────────────────────────────────────
  과업 ①  AMR 이동 경로 (Dijkstra)
      └─ path(), dist()

  과업 ②  스테이션 선택 정책
      ├─ select_next_machine()        — 다음 단계 설비 선택 (push)
      └─ select_upstream_source()     — 이전 스테이션의 후보 주문 선택 (pull)

  과업 ③  주문 투입 우선순위 정책
      └─ decide_next_order_type()     — Warehouse에 새로 만들 주문 유형

   AMR 배차 정책
      └─ select_amr()                 — 어느 AMR에 task를 배차할지

──────────────────────────────────────────────────────────────
사용 가능한 전역 상태 (core.config.global_variable)
──────────────────────────────────────────────────────────────
  global_variable.now                 시뮬레이션 현재 시각(초)
  global_variable.MACHINES            Dict[stage, List[Machine]]
  global_variable.AMRS                List[AMR]
  global_variable.WAREHOUSE           Warehouse 인스턴스
  global_variable.ROUND_ROBIN_IDX     Dict[stage, int]   (라운드로빈 카운터)
  global_variable.FEED_SEQ            현재 시나리오의 feed_sequence
  global_variable.FEED_IDX            feed_sequence 인덱스 카운터
  global_variable.CURRENT_CFG         FactoryConfig 인스턴스
"""

from typing import List, Optional, Tuple
from core.data_structures import Machine, Job, AMR
from core.config import global_variable, _peek_next_stage
from core.path_utils import path_length as _path_length  # 인프라(수정 불필요)
import heapq
import math
from typing import Tuple, List


# ════════════════════════════════════════════════════════════════
#  과업 ①  AMR 이동 경로 — Dijkstra 알고리즘 적용
# ════════════════════════════════════════════════════════════════

def path(a: Tuple[float, float], b: Tuple[float, float]) -> List[Tuple[float, float]]:
    """
    현재 구현 : 
      Dijkstra 미구현 — 단순 직선 이동.
      → AMR이 설비를 통과하는 비현실적 경로가 나옴.
      아래 "구현 영역" 안을 Dijkstra 로 교체할 것.

    a → b 까지 설비를 우회하는 waypoint 리스트를 반환.

    반환 형식
      [a, w1, w2, ..., b]   ← 시작·끝은 입력 좌표 그대로

    가용 정보
      - global_variable.MACHINES : Dict[stage, List[Machine]]
        · 각 머신의 중심 좌표와 점유 셀 범위를 잘 보고 통행 가능한 범위를 파악할 것


    이 함수가 자동으로 영향을 미치는 곳
      ① dist(a, b)  → ETA·KPI(makespan)
      ② amr_runs 로그 → 시뮬레이션 종료 후 애니메이션이
                       waypoint 를 따라 AMR 의 경로를 그림 (성공적으로 수정 시 우회가 가시적으로 보임)
      

    """
    # ════════════ 학생 구현 영역 시작 ════════════
    """
    a → b 까지 설비를 우회하는 waypoint 리스트를 반환.
    반환 형식: [a, w1, w2, ..., b]
    """

    # 전체 레이아웃 크기
    X_MIN, X_MAX = 0, 60
    Y_MIN, Y_MAX = 0, 20

    # 좌표를 격자 좌표로 변환
    start = (round(a[0]), round(a[1]))
    goal = (round(b[0]), round(b[1]))

    # -----------------------------
    # 1. 설비가 차지하는 칸을 장애물로 만들기
    # -----------------------------
    obstacles = set()

    for stage in global_variable.MACHINES:
        for machine in global_variable.MACHINES[stage]:

            # Machine 객체의 좌표 속성 이름이 코드마다 다를 수 있으므로
            # 가능한 경우를 여러 개 처리
            if hasattr(machine, "x") and hasattr(machine, "y"):
                mx, my = machine.x, machine.y
            elif hasattr(machine, "pos"):
                mx, my = machine.pos
            elif hasattr(machine, "position"):
                mx, my = machine.position
            else:
                # 좌표를 못 찾으면 일단 건너뜀
                continue

            mx = round(mx)
            my = round(my)

            # 설비 크기: 3m x 2m
            # 중심이 (mx, my)라고 보고 주변 칸을 막음
            # 약간 넉넉하게 y 방향도 my-1 ~ my+1까지 막아서
            # AMR이 설비를 스치며 통과하는 문제를 줄임
            for x in range(mx - 1, mx + 2):
                for y in range(my - 1, my + 2):
                    obstacles.add((x, y))

    # 시작점과 도착점은 포트 좌표일 수 있으므로 장애물에서 제외
    obstacles.discard(start)
    obstacles.discard(goal)

    # -----------------------------
    # 2. 격자 내부인지, 이동 가능한 칸인지 확인
    # -----------------------------
    def is_valid(node):
        x, y = node
        if x < X_MIN or x > X_MAX:
            return False
        if y < Y_MIN or y > Y_MAX:
            return False
        if node in obstacles:
            return False
        return True

    # 상하좌우 이동
    directions = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1)
    ]

    # -----------------------------
    # 3. Dijkstra 알고리즘
    # -----------------------------
    INF = float("inf")

    dist_table = {}
    prev = {}

    dist_table[start] = 0

    heap = []
    heapq.heappush(heap, (0, start))

    visited = set()

    while heap:
        current_dist, current = heapq.heappop(heap)

        if current in visited:
            continue

        visited.add(current)

        if current == goal:
            break

        for dx, dy in directions:
            nxt = (current[0] + dx, current[1] + dy)

            if not is_valid(nxt):
                continue

            new_dist = current_dist + 1

            if new_dist < dist_table.get(nxt, INF):
                dist_table[nxt] = new_dist
                prev[nxt] = current
                heapq.heappush(heap, (new_dist, nxt))

    # -----------------------------
    # 4. 경로 복원
    # -----------------------------
    if goal not in dist_table:
        # 경로를 못 찾은 경우 시뮬레이션이 멈추지 않도록 직선 경로 반환
        # 하지만 정상이라면 여기로 오면 안 됨
        return [a, b]

    grid_path = []
    cur = goal

    while cur != start:
        grid_path.append(cur)
        cur = prev[cur]

    grid_path.append(start)
    grid_path.reverse()

    # -----------------------------
    # 5. 불필요한 중간점 줄이기
    #    같은 방향으로 계속 가는 점들은 제거해서
    #    waypoint가 너무 길어지는 것을 방지
    # -----------------------------
    compressed = []

    for p in grid_path:
        if len(compressed) < 2:
            compressed.append(p)
        else:
            p1 = compressed[-2]
            p2 = compressed[-1]
            p3 = p

            dir1 = (p2[0] - p1[0], p2[1] - p1[1])
            dir2 = (p3[0] - p2[0], p3[1] - p2[1])

            if dir1 == dir2:
                compressed[-1] = p3
            else:
                compressed.append(p3)

    # 시작과 끝은 입력 좌표 그대로 유지해야 함
    result = [a]

    for p in compressed[1:-1]:
        result.append((float(p[0]), float(p[1])))

    result.append(b)

    return result
    # ════════════ 학생 구현 영역 끝   ════════════


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """
    두 점 사이의 이동 거리(시간 환산용) — path(a,b) 의 누적 호 길이.


    호출처: reserve_amr / _predict_eta_for_pick / select_amr /
            select_upstream_source('nearby') / select_next_machine 힌트.
    """
    return _path_length(a, b)


# ════════════════════════════════════════════════════════════════
#  과업 ②-1  다음 단계 설비 선택
# ════════════════════════════════════════════════════════════════

def select_next_machine(stage: str, candidates: List[Machine]) -> Machine:
    """
    동일 종류 설비가 여러 대 있을 때, 어느 설비로 주문을 보낼지 선택.

    호출 위치
      - move_to_next_stage_from_output : 처리 완료 후 다음 스테이션 선택
      - try_dispatch_from_warehouse_to_R : Warehouse에서 R 스테이션 선택

    ▶ 현재: 라운드로빈(ROUND_ROBIN_IDX 기반 순차 배정).

    """
    rr = global_variable.ROUND_ROBIN_IDX.get(stage, 0)
    drop_m = candidates[rr % len(candidates)]
    global_variable.ROUND_ROBIN_IDX[stage] = rr + 1
    return drop_m


# ════════════════════════════════════════════════════════════════
#  과업 ②-2  이전 스테이션의 후보 주문 선택 (Pull)
# ════════════════════════════════════════════════════════════════

def select_upstream_source(
    prev_machines: List[Machine],
    drop_xy: Tuple[float, float],
    target_stage: Optional[str] = None,
) -> Optional[Tuple[Machine, Job]]:
    """
    다음 설비(m_next)의 input 슬롯이 비었을 때,
    이전 스테이션 중 '지금 보낼 수 있는' 후보 1건을 선택.

    target_stage 필터 (자동):
      각 후보 job의 다음 스테이지가 target_stage와 일치해야 함.
      예) K가 P에서 끌어올 때 Std 주문만 허용 (Exp/Cld는 I/F로 가야 함).
      I/F의 주문 유형 정합성도 이 필터로 보장됨.

    ▶ 현재: drop_xy 와의 거리가 가장 가까운 후보 1건 선택 (단순 최근접).

    """
    cands = []
    for m in prev_machines:
        job = m.output_buf
        if job is None or job.reserved or job.in_transit:
            continue

        if target_stage is not None:
            if _peek_next_stage(job, m.stage) != target_stage:
                continue

        pick_xy = m.output_port
        score   = dist(pick_xy, drop_xy)
        cands.append((score, m, job))

    if not cands:
        return None

    cands.sort(key=lambda x: (x[0], getattr(x[2], "job_id", ""), x[1].name))
    _, src_m, job = cands[0]
    return src_m, job


# ════════════════════════════════════════════════════════════════
#  과업 ③  주문 투입 우선순위 정책
# ════════════════════════════════════════════════════════════════

def decide_next_order_type() -> str:
    """
    Warehouse에 새 주문을 생성할 때 어떤 유형(Std/Exp/Cld)을 만들지 결정.

    ▶ 현재: feed_sequence를 순환하며 정해진 순서대로 투입 (정적).
       I 스테이션이 비어있어도 Std만 계속 투입 → I 낭비.


    ▶ 제약 (가이드라인)
      - 시나리오 비율 자체는 변경 불가
      - 전체 시뮬레이션 종료 시점에 실제 투입 비율이 시나리오 비율 ±3% 이내
    """
    if not global_variable.FEED_SEQ:
        return "Std"
    seq = global_variable.FEED_SEQ
    idx = global_variable.FEED_IDX % len(seq)
    global_variable.FEED_IDX += 1
    return seq[idx]


# ════════════════════════════════════════════════════════════════
#  AMR 배차 정책
# ════════════════════════════════════════════════════════════════

def select_amr(
    amrs: List[AMR],
    pick_xy: Tuple[float, float],
    drop_xy: Tuple[float, float],
    request_time: float,
    load_sec: float,
    unload_sec: float,
    job_id: Optional[str] = None,
) -> AMR:
    """
    여러 AMR 중 어느 로봇에 이 task(pick → drop)를 배차할지 결정.
    선택만 책임지며, free_time / planned_xy 같은 상태 업데이트와
    콜백 등록은 core/scheduling.py 의 reserve_amr 가 처리한다.

    ▶ 현재: depart_drop(=ETA) 최소 AMR 선택.
       시뮬레이션 끝나는 시각이 가장 빠른 AMR 1대.

    주의
      - 반환값이 None이거나 amrs에 없는 AMR이면 시뮬레이션이 깨진다.
      - amr.free_time / amr.planned_xy 는 절대 직접 수정하지 말 것.
        (해당 상태 업데이트는 reserve_amr가 책임)
    """
    best, best_eta = amrs[0], float("inf")
    for a in amrs:
        depart_at    = max(request_time, a.free_time)
        future_start = (
            a.planned_xy
            if (a.planned_xy is not None and a.free_time > request_time)
            else a.xy
        )
        t_pick = dist(future_start, pick_xy) / max(a.speed, 1e-9)
        t_drop = dist(pick_xy, drop_xy)      / max(a.speed, 1e-9)
        eta    = depart_at + t_pick + load_sec + t_drop + unload_sec
        if eta < best_eta:
            best, best_eta = a, eta
    return best



"""
이쪽에 위의 함수들 외에도 추가적인 기능을 하는 함수들을 자유롭게 구현해도 좋습니다. 
다만, core/scheduling.py 의 이벤트 콜백과 같이 시뮬레이션의 뼈대를 담당하는 함수들을 수정해야 한다면, 꼭 수정한 부분과 이유를 주석으로 명확히 언급해주세요.
"""
