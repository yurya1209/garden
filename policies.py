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
    return [a, b]
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