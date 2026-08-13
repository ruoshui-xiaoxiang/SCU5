# -*- coding: utf-8 -*-
"""
m_layer/evolution/unit_pair.py — 单元对生命周期与协作生态（M层）
================================================================
太极熵税模型的核心实现：将熵税从"资源配额"升级为"对子生命力"。

核心机制：
  1. 阴消阳长守恒：阴/阳单元共用势能池，E_yin + E_yang = E_total
     - 阳操作消耗阳势能→转为阴势能（阳降阴升）
     - 阴操作消耗阴势能→转为阳势能（阴降阳升）
  2. 偏度度量：b = (E_yang - E_yin) / E_total，范围 [-1, 1]
  3. 回调成本递增：C(b) = k * (exp(α*|b|) - 1)，指数方案
     - 小偏度时回调便宜（鼓励及时回调）
     - 大偏度时极贵（急剧偏向迅速致命）
  4. 对子自判回调：|b| 超过自判阈值时主动触发中和融合
  5. 自然死亡：C(b) > E_total（付不起回调代价），无需外加判定
  6. 分工协作：多对子并存，偏度互补融合→集体势能回充

架构归属：M层（元认知层，协调认知+经验+账本）
依赖方向：M→W1（调用账本）、M→M（调用认知回调）、M→W1（经验存储）
合规：不修改D层常量，偏度系数在W1层运行时叠加
"""
import os
import sys
import json
import math
import time
import uuid
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable
from datetime import datetime
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from d_layer.axioms import INITIAL_BUDGET, MIN_BALANCE

logger = logging.getLogger("SCU3.m.unit_pair")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "SCU3_data")
PAIR_STATE_PATH = os.path.join(DATA_DIR, "unit_pairs.json")


# ═══ 常量参数 ═══════════════════════════════════════════════

# 回调成本函数参数：C(b) = k * (exp(α * |b|/(1-|b|)) - 1)
# 在 b→1 时真正发散（无限偏向需无限势能）
CALLBACK_COST_K = 5.0       # 基础成本系数
CALLBACK_COST_ALPHA = 0.3   # 指数陡度（控制小偏度区间的斜率）
CALLBACK_COST_EPSILON = 0.001  # 防止除零

# 对子自判回调阈值：|b| 超过此值时主动触发中和融合
SELF_CALLBACK_THRESHOLD = 0.3

# 回调成功时的势能回充量（中和融合产生新势能）
FUSION_REPLENISH = 50.0

# 回调失败时的偏度缓解（部分回调，偏度略降）
FAILED_CALLBACK_RELIEF = 0.05

# 协同融合势能回充（多对子偏度互补时）
SYNERGY_REPLENISH = 30.0

# 对子最大势能上限（防止无限回充）
MAX_ENERGY = 2000.0


# ═══ 偏度追踪器 ════════════════════════════════════════════

class PolarizationTracker:
    """偏度追踪器 — 记录操作历史，计算当前偏度

    偏度由势能分布决定：b = (E_yang - E_yin) / E_total
    范围 [-1, 1]：-1=极阴，0=中和，+1=极阳
    """

    def __init__(self, e_yin: float = 0.0, e_yang: float = 0.0):
        self._e_yin = e_yin   # 阴势能
        self._e_yang = e_yang  # 阳势能
        self._op_history: deque = deque(maxlen=100)  # 操作历史

    @property
    def e_yin(self) -> float:
        return self._e_yin

    @property
    def e_yang(self) -> float:
        return self._e_yang

    @property
    def e_total(self) -> float:
        """总势能（守恒量）"""
        return self._e_yin + self._e_yang

    def bias(self) -> float:
        """当前偏度 [-1, 1]"""
        total = self.e_total
        if total < 1e-9:
            return 0.0
        return (self._e_yang - self._e_yin) / total

    def stability(self) -> float:
        """稳定度 [0, 1]，偏度绝对值越小越稳定"""
        return 1.0 - abs(self.bias())

    def transfer_yin_to_yang(self, amount: float) -> float:
        """阴操作：消耗阴势能→转为阳势能（阴降阳升）

        Args:
            amount: 转移量

        Returns:
            实际转移量（可能因阴势能不足而截断）
        """
        actual = min(amount, self._e_yin)
        self._e_yin -= actual
        self._e_yang += actual
        self._op_history.append(("yin", actual, time.time()))
        return actual

    def transfer_yang_to_yin(self, amount: float) -> float:
        """阳操作：消耗阳势能→转为阴势能（阳降阴升）"""
        actual = min(amount, self._e_yang)
        self._e_yang -= actual
        self._e_yin += actual
        self._op_history.append(("yang", actual, time.time()))
        return actual

    def replenish(self, amount: float, to: str = "balanced") -> None:
        """回充势能（中和融合产生新势能）

        Args:
            amount: 回充量
            to: "yin"/"yang"/"balanced"(各半)
        """
        amount = min(amount, MAX_ENERGY - self.e_total)
        if amount <= 0:
            return
        if to == "yin":
            self._e_yin += amount
        elif to == "yang":
            self._e_yang += amount
        else:
            self._e_yin += amount / 2
            self._e_yang += amount / 2
        self._op_history.append(("replenish", amount, time.time()))

    def callback_cost(self) -> float:
        """回调成本 C(b) = k * (exp(α * |b|/(1-|b|)) - 1)

        偏度越大回调越贵；|b|→1时C→∞（无限偏向需无限势能）
        """
        b = abs(self.bias())
        # b/(1-b) 在 b→1 时发散，使成本真正趋向无穷
        divergent_term = b / max(1.0 - b, CALLBACK_COST_EPSILON)
        return CALLBACK_COST_K * (math.exp(CALLBACK_COST_ALPHA * divergent_term) - 1)

    def can_callback(self) -> bool:
        """是否能付得起回调代价"""
        return self.e_total >= self.callback_cost()

    def needs_callback(self) -> bool:
        """是否需要回调（对子自判：偏度超过阈值）"""
        return abs(self.bias()) > SELF_CALLBACK_THRESHOLD

    def pay_callback(self) -> Tuple[bool, float, str]:
        """支付回调成本

        Returns:
            (success, cost_paid, reason)
        """
        cost = self.callback_cost()
        if self.e_total < cost:
            return False, 0.0, f"付不起回调代价: C={cost:.2f} > E={self.e_total:.2f}"

        # 从偏多的那极扣除（回调是"把偏多的一极拉回"）
        b = self.bias()
        if b > 0:  # 偏阳，从阳扣
            # 扣除时势能消失（不转移，是真正的消耗）
            self._e_yang -= cost
        else:  # 偏阴，从阴扣
            self._e_yin -= cost
        self._op_history.append(("callback_pay", cost, time.time()))
        return True, cost, f"已支付回调代价 {cost:.2f}E"

    def rebalance_after_fusion(self, success: bool) -> None:
        """回调（中和融合）后的偏度调整

        Args:
            success: 融合是否成功
        """
        if success:
            # 融合成功：偏度归零 + 势能回充
            total = self.e_total
            self._e_yin = total / 2
            self._e_yang = total / 2
            self.replenish(FUSION_REPLENISH, "balanced")
        else:
            # 融合失败：偏度略降（部分回调）
            b = self.bias()
            relief = FAILED_CALLBACK_RELIEF
            if b > 0:
                # 偏阳，少量阳转阴
                transfer = min(self._e_yang * relief, self._e_yang)
                self._e_yang -= transfer
                self._e_yin += transfer
            else:
                transfer = min(self._e_yin * relief, self._e_yin)
                self._e_yin -= transfer
                self._e_yang += transfer

    def to_dict(self) -> Dict[str, Any]:
        return {
            "e_yin": round(self._e_yin, 4),
            "e_yang": round(self._e_yang, 4),
            "e_total": round(self.e_total, 4),
            "bias": round(self.bias(), 4),
            "stability": round(self.stability(), 4),
            "callback_cost": round(self.callback_cost(), 4),
            "needs_callback": self.needs_callback(),
            "can_callback": self.can_callback(),
        }


# ═══ 单元对 ════════════════════════════════════════════════

class UnitPair:
    """单元对 — 阴阳两单元组成的活体生命

    生命周期：诞生→运行→偏度累积→自判回调→续命/死亡→经验回收→重生

    属性：
        pair_id: 对子唯一ID
        specialty: 分工专长（search/analysis/writing/coding/general）
        tracker: 偏度追踪器
        gamma_history: γ_yin/γ_yang 历史序列
        callback_attempts: 回调尝试次数
        last_callback_result: 最近回调结果
        is_alive: 是否存活
        born_at: 诞生时间
        task_context: 当前任务上下文
    """

    # 生命周期状态
    STATE_BORN = "born"          # 刚诞生
    STATE_RUNNING = "running"    # 运行中
    STATE_CALLBACK = "callback"  # 回调中
    STATE_DYING = "dying"        # 濒死（经验回收中）
    STATE_DEAD = "dead"          # 已死亡
    STATE_REBORN = "reborn"      # 重生（新对子继承经验）

    def __init__(self, pair_id: str = "", specialty: str = "general",
                 initial_energy: float = INITIAL_BUDGET,
                 inherited_experience: Optional[Dict] = None):
        self.pair_id = pair_id or f"pair_{uuid.uuid4().hex[:8]}"
        self.specialty = specialty
        self.state = self.STATE_BORN
        self.born_at = datetime.now().isoformat()
        self.tracker = PolarizationTracker(
            e_yin=initial_energy / 2,
            e_yang=initial_energy / 2,
        )
        self.gamma_history: deque = deque(maxlen=50)
        self.callback_attempts = 0
        self.last_callback_result: Optional[bool] = None
        # 方案2：回调上下文（由 cognition 注入，供 _do_callback 使用）
        self.callback_context = {}  # {user_input, rag_context, handler}
        self.last_callback_response = None  # 双签生成的回复
        self.is_alive = True
        self.task_context: Optional[str] = None
        self.inherited_experience = inherited_experience or {}
        self._trajectory: List[Dict] = []  # 完整思考轨迹（死亡时回收）

        # 根据专长设置初始偏度倾向（分工的自然偏度）
        self._apply_specialty_bias()

        logger.info(f"单元对诞生: {self.pair_id} (专长={specialty}, "
                    f"势能={self.tracker.e_total:.1f}E, "
                    f"初始偏度={self.tracker.bias():.2f})")

    def _apply_specialty_bias(self):
        """根据专长设置初始偏度倾向（分工的自然偏度）

        不同专长天然偏向不同极：
        - search/analysis: 偏阴（收敛、校验）
        - writing/coding: 偏阳（生成、扩张）
        - general: 中和
        """
        bias_map = {
            "search": -0.15,    # 偏阴
            "analysis": -0.20,  # 偏阴
            "writing": 0.15,    # 偏阳
            "coding": 0.20,     # 偏阳
            "general": 0.0,     # 中和
        }
        target_bias = bias_map.get(self.specialty, 0.0)
        if target_bias != 0:
            total = self.tracker.e_total
            # 调整势能分布以产生目标偏度
            self.tracker._e_yin = total * (1 - target_bias) / 2
            self.tracker._e_yang = total * (1 + target_bias) / 2

    # ─── 运行：操作计税 ────────────────────────────

    def execute_yin_op(self, cost: float, reason: str = "") -> Tuple[bool, str]:
        """执行阴操作（校验、只读、批判）

        阴操作消耗阴势能→转为阳势能（阴降阳升）
        """
        if not self.is_alive:
            return False, "对子已死亡"

        transferred = self.tracker.transfer_yin_to_yang(cost)
        self._trajectory.append({
            "type": "yin_op", "cost": cost, "transferred": transferred,
            "reason": reason, "bias_after": self.tracker.bias(),
            "ts": datetime.now().isoformat(),
        })

        # 操作后检查是否需要回调
        if self.tracker.needs_callback():
            return self._trigger_callback(reason=f"阴操作后偏度={self.tracker.bias():.2f}")

        return True, f"阴操作完成，偏度={self.tracker.bias():.2f}"

    def execute_yang_op(self, cost: float, reason: str = "") -> Tuple[bool, str]:
        """执行阳操作（生成、写、扩张）

        阳操作消耗阳势能→转为阴势能（阳降阴升）
        """
        if not self.is_alive:
            return False, "对子已死亡"

        transferred = self.tracker.transfer_yang_to_yin(cost)
        self._trajectory.append({
            "type": "yang_op", "cost": cost, "transferred": transferred,
            "reason": reason, "bias_after": self.tracker.bias(),
            "ts": datetime.now().isoformat(),
        })

        if self.tracker.needs_callback():
            return self._trigger_callback(reason=f"阳操作后偏度={self.tracker.bias():.2f}")

        return True, f"阳操作完成，偏度={self.tracker.bias():.2f}"

    # ─── 回调机制 ────────────────────────────────

    def _trigger_callback(self, reason: str = "") -> Tuple[bool, str]:
        """触发回调（中和融合尝试）

        对子自判：偏度超过阈值时主动触发
        回调消耗势能 C(b)，偏度越大越贵
        回调成功→偏度归零+势能回充（续命）
        回调失败→偏度略降（部分缓解）
        C(b)>E→自然死亡
        """
        if not self.is_alive:
            return False, "对子已死亡"

        self.state = self.STATE_CALLBACK
        self.callback_attempts += 1

        # 检查是否能付得起回调代价
        if not self.tracker.can_callback():
            # 付不起回调代价 → 自然死亡
            return self._die(reason=f"回调代价超出势能: "
                                    f"C={self.tracker.callback_cost():.2f} > "
                                    f"E={self.tracker.e_total:.2f}")

        # 支付回调代价
        paid_ok, cost, pay_msg = self.tracker.pay_callback()
        if not paid_ok:
            return self._die(reason=pay_msg)

        logger.info(f"对子 {self.pair_id} 触发回调 #{self.callback_attempts} "
                    f"(偏度={self.tracker.bias():.2f}, 代价={cost:.2f}E, 原因={reason})")

        # 调用实际的回调机制（由外部注入，默认为内置判定）
        # 真实接入时由 cognition._yin_yang_think 执行
        callback_result = self._do_callback()

        # 回调后偏度调整
        self.tracker.rebalance_after_fusion(callback_result)
        self.last_callback_result = callback_result

        if callback_result:
            self.state = self.STATE_RUNNING
            logger.info(f"对子 {self.pair_id} 回调成功，续命 "
                        f"(偏度={self.tracker.bias():.2f}, "
                        f"势能={self.tracker.e_total:.2f}E)")
            return True, f"回调成功，续命"
        else:
            # 回调失败，检查是否还能继续
            if self.tracker.can_callback():
                self.state = self.STATE_RUNNING
                return True, f"回调失败但势能尚存，继续运行"
            else:
                return self._die(reason="回调失败且势能耗尽")

    def _do_callback(self) -> bool:
        """执行实际回调（中和融合）

        方案2：若 callback_context 中有 cognition 注入的处理器，执行阴阳双签
        默认实现：基于γ历史的质量判定
        """
        # 方案2：cognition 注入的回调处理器
        handler = self.callback_context.get("handler")
        if handler:
            try:
                result = handler(self, self.callback_context)
                if isinstance(result, dict):
                    self.last_callback_response = result.get("response", "")
                    self.record_gamma(
                        result.get("gamma_yin", 0.5),
                        result.get("gamma_yang", 0.5),
                    )
                    return result.get("success", True)
                return bool(result)
            except Exception as e:
                logger.warning(f"双签回调异常，降级到默认: {e}")

        # 默认实现：基于γ历史的质量判定
        if not self.gamma_history:
            return True
        recent = list(self.gamma_history)[-5:]
        avg_quality = sum(g.get("gamma_avg", 0.5) for g in recent) / len(recent)
        return avg_quality > 0.5

    def record_gamma(self, gamma_yin: float, gamma_yang: float) -> None:
        """记录阴阳质量分（供回调判定使用）"""
        self.gamma_history.append({
            "gamma_yin": gamma_yin,
            "gamma_yang": gamma_yang,
            "gamma_avg": (gamma_yin + gamma_yang) / 2,
            "bias": self.tracker.bias(),
            "ts": datetime.now().isoformat(),
        })

    # ─── 死亡与经验回收 ────────────────────────────

    def _die(self, reason: str) -> Tuple[bool, str]:
        """对子死亡 — 经验回收"""
        self.state = self.STATE_DYING
        self.is_alive = False

        death_record = {
            "pair_id": self.pair_id,
            "specialty": self.specialty,
            "born_at": self.born_at,
            "died_at": datetime.now().isoformat(),
            "death_reason": reason,
            "callback_attempts": self.callback_attempts,
            "final_bias": self.tracker.bias(),
            "final_energy": self.tracker.e_total,
            "gamma_history": list(self.gamma_history),
            "trajectory": self._trajectory,
            "task_context": self.task_context,
        }

        logger.warning(f"对子死亡: {self.pair_id} ({reason})")
        self.death_record = death_record
        self.state = self.STATE_DEAD
        return False, f"对子死亡: {reason}"

    def collect_experience(self) -> Optional[Dict]:
        """回收完整轨迹（死亡后调用）"""
        if self.is_alive:
            return None
        return getattr(self, "death_record", None)

    # ─── 协作：势能借贷 ────────────────────────────

    def can_lend_energy(self, amount: float) -> bool:
        """是否能借出势能（自身势能充足且稳定度高）"""
        return (self.is_alive and
                self.tracker.e_total > amount * 2 and
                self.tracker.stability() > 0.6)

    def lend_energy(self, amount: float, to_pair: "UnitPair") -> Tuple[bool, str]:
        """向另一对子借出势能（偏度互补）"""
        if not self.can_lend_energy(amount):
            return False, "无法借出（势能不足或稳定度低）"

        # 从偏多的一极借出
        if self.tracker.bias() > 0:  # 偏阳，借阳
            self.tracker._e_yang -= amount
            to_pair.tracker.replenish(amount, "yang")
        else:  # 偏阴，借阴
            self.tracker._e_yin -= amount
            to_pair.tracker.replenish(amount, "yin")

        logger.info(f"势能借贷: {self.pair_id} → {to_pair.pair_id} ({amount:.1f}E)")
        return True, f"借出 {amount:.1f}E 给 {to_pair.pair_id}"

    # ─── 状态查询 ────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "specialty": self.specialty,
            "state": self.state,
            "is_alive": self.is_alive,
            "born_at": self.born_at,
            "callback_attempts": self.callback_attempts,
            "last_callback_result": self.last_callback_result,
            "tracker": self.tracker.to_dict(),
            "gamma_count": len(self.gamma_history),
            "trajectory_count": len(self._trajectory),
            "task_context": self.task_context,
        }


# ═══ 对子协作生态 ══════════════════════════════════════════

class PairEcosystem:
    """对子协作生态 — 管理多对子的分工协作

    核心能力：
      1. 对子池管理：创建、查询、回收对子
      2. 分工协作：按专长分配任务给对子
      3. 偏度互补：识别偏度互补的对子组合
      4. 协同融合：多对子产出融合→集体势能回充
      5. 势能借贷：偏多对子借给偏少对子
      6. 经验传承：死亡对子经验→新对子预加载避坑
      7. 持久化：对子状态保存到 SCU3_data/unit_pairs.json

    性能优化：
      - 延迟持久化：内存即时更新，写盘由后台线程每 N 秒/每 M 次触发
      - 对子查找缓存：按 specialty 缓存当前最佳对子，避免每次遍历
      - 异步回调：标记 needs_callback 后由后台线程执行，不阻塞主流程
    """

    # 延迟持久化参数
    PERSIST_INTERVAL = 5.0       # 后台刷盘间隔（秒）
    PERSIST_DIRTY_THRESHOLD = 8  # 累积脏操作次数阈值（达到即刷盘）

    # 异步回调参数
    CALLBACK_THREAD_INTERVAL = 2.0  # 回调检测线程间隔（秒）

    def __init__(self):
        self._lock = threading.RLock()
        self._pairs: Dict[str, UnitPair] = {}
        self._dirty_count = 0            # 自上次刷盘以来的脏操作计数
        self._dirty_flag = False         # 是否有未持久化的变更
        self._persist_thread: Optional[threading.Thread] = None
        self._callback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # 对子查找缓存: {specialty: (pair_id, stability_snapshot)}
        self._best_pair_cache: Dict[str, Tuple[str, float]] = {}
        # 待执行回调队列: [(pair_id, reason), ...]
        self._pending_callbacks: List[Tuple[str, str]] = []
        self._load()
        self._start_background_threads()

    # ─── 后台线程 ────────────────────────────────

    def _start_background_threads(self):
        """启动后台持久化线程和回调线程"""
        self._persist_thread = threading.Thread(
            target=self._persist_loop, name="pair-persist", daemon=True)
        self._persist_thread.start()
        self._callback_thread = threading.Thread(
            target=self._callback_loop, name="pair-callback", daemon=True)
        self._callback_thread.start()
        logger.info("对子生态后台线程已启动 (持久化+回调)")

    def _persist_loop(self):
        """后台持久化循环：定时刷盘"""
        while not self._stop_event.wait(self.PERSIST_INTERVAL):
            try:
                if self._dirty_flag:
                    self._save()
                    self._dirty_flag = False
                    self._dirty_count = 0
            except Exception as e:
                logger.warning(f"后台持久化失败: {e}")

    def _callback_loop(self):
        """后台回调循环：检测并执行待回调对子"""
        while not self._stop_event.wait(self.CALLBACK_THREAD_INTERVAL):
            try:
                self._process_pending_callbacks()
            except Exception as e:
                logger.warning(f"后台回调处理失败: {e}")

    def _process_pending_callbacks(self):
        """处理待回调队列"""
        with self._lock:
            if not self._pending_callbacks:
                return
            pending = self._pending_callbacks[:]
            self._pending_callbacks.clear()

        for pair_id, reason in pending:
            pair = self._pairs.get(pair_id)
            if pair is None or not pair.is_alive:
                continue
            try:
                # 后台执行回调（不阻塞主流程）
                ok, msg = pair._trigger_callback(reason=reason)
                logger.info(f"对子 {pair_id} 后台回调: ok={ok}, msg={msg}")
                self._mark_dirty()
            except Exception as e:
                logger.warning(f"对子 {pair_id} 后台回调异常: {e}")

    def _mark_dirty(self):
        """标记有未持久化变更（替代直接 _save）"""
        self._dirty_flag = True
        self._dirty_count += 1
        # 达到阈值立即触发刷盘
        if self._dirty_count >= self.PERSIST_DIRTY_THRESHOLD:
            try:
                self._save()
                self._dirty_flag = False
                self._dirty_count = 0
            except Exception as e:
                logger.warning(f"阈值触发持久化失败: {e}")

    def _invalidate_cache(self, specialty: str = ""):
        """使查找缓存失效"""
        if specialty:
            self._best_pair_cache.pop(specialty, None)
        else:
            self._best_pair_cache.clear()

    def shutdown(self):
        """关闭后台线程（用于进程退出前确保刷盘）"""
        self._stop_event.set()
        # 最后一次刷盘
        try:
            if self._dirty_flag:
                self._save()
        except Exception:
            pass

    # ─── 对子生命周期管理 ────────────────────────

    def spawn_pair(self, specialty: str = "general",
                   initial_energy: float = INITIAL_BUDGET,
                   inherited_experience: Optional[Dict] = None) -> UnitPair:
        """诞生新对子（刷新势能）"""
        with self._lock:
            pair = UnitPair(
                specialty=specialty,
                initial_energy=initial_energy,
                inherited_experience=inherited_experience,
            )
            self._pairs[pair.pair_id] = pair
            self._invalidate_cache(specialty)
            self._mark_dirty()
            logger.info(f"生态诞生新对子: {pair.pair_id} (专长={specialty})")
            return pair

    def get_pair(self, pair_id: str) -> Optional[UnitPair]:
        with self._lock:
            return self._pairs.get(pair_id)

    def get_alive_pairs(self, specialty: str = "") -> List[UnitPair]:
        """获取存活的对子（可按专长过滤）"""
        with self._lock:
            pairs = [p for p in self._pairs.values() if p.is_alive]
            if specialty:
                pairs = [p for p in pairs if p.specialty == specialty]
            return pairs

    def get_best_pair_for_task(self, specialty: str) -> Optional[UnitPair]:
        """获取最适合某专长的对子（稳定度最高，带缓存）"""
        with self._lock:
            # 1. 检查缓存
            cached = self._best_pair_cache.get(specialty)
            if cached:
                pair_id, cached_stability = cached
                pair = self._pairs.get(pair_id)
                # 缓存有效条件：对子存在、存活、稳定度未显著变化
                if (pair and pair.is_alive and
                        abs(pair.tracker.stability() - cached_stability) < 0.05):
                    return pair
                # 缓存失效
                self._best_pair_cache.pop(specialty, None)

            # 2. 遍历查找
            pairs = [p for p in self._pairs.values()
                     if p.is_alive and p.specialty == specialty]
            if not pairs:
                # 无合适对子，诞生新的（spawn_pair 内部会更新缓存）
                return self.spawn_pair(specialty)

            # 选稳定度最高的
            best = max(pairs, key=lambda p: p.tracker.stability())
            # 更新缓存
            self._best_pair_cache[specialty] = (best.pair_id, best.tracker.stability())
            return best

    # ─── 分工协作 ────────────────────────────────

    def dispatch_task(self, specialty: str, task_context: str,
                      executor: Optional[Callable] = None) -> Dict[str, Any]:
        """分配任务给对子

        Args:
            specialty: 任务专长
            task_context: 任务内容
            executor: 执行函数（接收pair和task_context，返回结果）

        Returns:
            {pair_id, success, result, pair_state}
        """
        pair = self.get_best_pair_for_task(specialty)
        pair.task_context = task_context

        if executor is None:
            return {"pair_id": pair.pair_id, "success": True,
                    "result": None, "pair_state": pair.to_dict()}

        try:
            result = executor(pair, task_context)
            return {"pair_id": pair.pair_id, "success": True,
                    "result": result, "pair_state": pair.to_dict()}
        except Exception as e:
            logger.error(f"对子 {pair.pair_id} 执行任务失败: {e}")
            return {"pair_id": pair.pair_id, "success": False,
                    "result": None, "error": str(e),
                    "pair_state": pair.to_dict()}

    # ─── 异步回调调度 ────────────────────────────

    def schedule_async_callback(self, pair_id: str, reason: str = "") -> None:
        """调度异步回调（不阻塞主流程）

        主流程执行操作后若发现 needs_callback，调用此方法将对子加入待回调队列。
        实际回调由后台 _callback_loop 线程执行。
        """
        with self._lock:
            # 避免重复入队
            existing_ids = {pid for pid, _ in self._pending_callbacks}
            if pair_id not in existing_ids:
                self._pending_callbacks.append((pair_id, reason))
                logger.debug(f"对子 {pair_id} 已加入异步回调队列 (原因: {reason})")

    # ─── 协同融合 ────────────────────────────────

    def synergy_fusion(self, pair_ids: List[str]) -> Tuple[bool, str, float]:
        """多对子协同融合

        偏度互补的对子组合融合→集体势能回充
        偏度共振（全同极）的对子组合→融合失败，集体消耗

        Returns:
            (success, message, replenish_amount)
        """
        with self._lock:
            pairs = [self._pairs[pid] for pid in pair_ids
                     if pid in self._pairs and self._pairs[pid].is_alive]
            if len(pairs) < 2:
                return False, "协同融合需至少2个存活对子", 0.0

            # 计算集体偏度
            biases = [p.tracker.bias() for p in pairs]
            avg_bias = sum(biases) / len(biases)
            # 偏度方差：越小越互补
            bias_variance = sum((b - avg_bias) ** 2 for b in biases) / len(biases)

            if bias_variance < 0.01:
                # 偏度共振（全同极），融合失败
                for p in pairs:
                    p.tracker.pay_callback()  # 集体消耗回调代价
                return False, f"偏度共振(方差={bias_variance:.3f})，融合失败", 0.0

            # 偏度互补，融合成功
            total_replenish = SYNERGY_REPLENISH * len(pairs)
            for p in pairs:
                p.tracker.replenish(SYNERGY_REPLENISH, "balanced")
                p.state = UnitPair.STATE_RUNNING

            # 融合改变了势能分布，失效缓存
            for p in pairs:
                self._invalidate_cache(p.specialty)
            self._mark_dirty()
            logger.info(f"协同融合成功: {len(pairs)}个对子, "
                        f"集体回充 {total_replenish:.1f}E, "
                        f"偏度方差={bias_variance:.3f}")
            return True, f"协同融合成功，回充 {total_replenish:.1f}E", total_replenish

    # ─── 势能借贷 ────────────────────────────────

    def auto_lending(self) -> int:
        """自动势能借贷：偏多对子借给偏少对子

        Returns:
            借贷次数
        """
        with self._lock:
            alive = self.get_alive_pairs()
            if len(alive) < 2:
                return 0

            # 按势能排序
            lenders = [p for p in alive if p.tracker.e_total > INITIAL_BUDGET * 0.5]
            borrowers = [p for p in alive if p.tracker.e_total < INITIAL_BUDGET * 0.3]

            count = 0
            for borrower in borrowers:
                for lender in lenders:
                    if lender.pair_id == borrower.pair_id:
                        continue
                    lend_amount = min(50.0, lender.tracker.e_total * 0.1)
                    ok, _ = lender.lend_energy(lend_amount, borrower)
                    if ok:
                        count += 1
                        break
            return count

    # ─── 经验回收与传承 ────────────────────────────

    def collect_dead_experiences(self) -> List[Dict]:
        """回收所有死亡对子的完整轨迹"""
        with self._lock:
            experiences = []
            dead_ids = []
            for pid, pair in self._pairs.items():
                if not pair.is_alive:
                    exp = pair.collect_experience()
                    if exp:
                        experiences.append(exp)
                        dead_ids.append(pid)

            # 清理已回收的死亡对子
            for pid in dead_ids:
                del self._pairs[pid]

            if experiences:
                self._invalidate_cache()
                self._mark_dirty()
                logger.info(f"回收 {len(experiences)} 个死亡对子的经验轨迹")
            return experiences

    def spawn_with_experience(self, specialty: str,
                              task_pattern: str = "") -> UnitPair:
        """带经验预加载诞生新对子（避坑）"""
        # 从经验库查询匹配的失败经验
        inherited = None
        try:
            from m_layer.evolution.experience_store import get_experience_store
            store = get_experience_store()
            # 查询是否有相关失败经验
            for exp in store.list_experiences():
                if (exp.get("fail_count", 0) > 0 and
                    task_pattern and task_pattern in exp.get("pattern", "")):
                    inherited = exp
                    break
        except Exception as e:
            logger.debug(f"经验预加载查询失败: {e}")

        return self.spawn_pair(specialty, inherited_experience=inherited)

    # ─── 持久化 ────────────────────────────────

    def _save(self):
        """保存对子状态"""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            data = {
                "pairs": {pid: p.to_dict() for pid, p in self._pairs.items()
                          if p.is_alive},
                "updated_at": datetime.now().isoformat(),
            }
            tmp_path = PAIR_STATE_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PAIR_STATE_PATH)
        except Exception as e:
            logger.warning(f"对子状态保存失败: {e}")

    def _load(self):
        """加载对子状态"""
        if not os.path.exists(PAIR_STATE_PATH):
            return
        try:
            with open(PAIR_STATE_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for pid, pdata in data.get("pairs", {}).items():
                # 重建对子
                pair = UnitPair(
                    pair_id=pid,
                    specialty=pdata.get("specialty", "general"),
                    initial_energy=pdata.get("tracker", {}).get("e_total",
                                                                INITIAL_BUDGET),
                )
                pair.state = UnitPair.STATE_RUNNING
                pair.born_at = pdata.get("born_at", pair.born_at)
                pair.callback_attempts = pdata.get("callback_attempts", 0)
                # 恢复势能分布
                tracker_data = pdata.get("tracker", {})
                pair.tracker._e_yin = tracker_data.get("e_yin",
                                                       pair.tracker.e_total / 2)
                pair.tracker._e_yang = tracker_data.get("e_yang",
                                                        pair.tracker.e_total / 2)
                self._pairs[pid] = pair
            if self._pairs:
                logger.info(f"对子生态加载: {len(self._pairs)} 个存活对子")
        except Exception as e:
            logger.warning(f"对子状态加载失败: {e}")

    # ─── 状态查询 ────────────────────────────────

    def status(self) -> Dict[str, Any]:
        with self._lock:
            alive = [p for p in self._pairs.values() if p.is_alive]
            return {
                "total_pairs": len(self._pairs),
                "alive_pairs": len(alive),
                "pairs": [p.to_dict() for p in alive],
                "total_energy": sum(p.tracker.e_total for p in alive),
                "avg_stability": (sum(p.tracker.stability() for p in alive) / len(alive)
                                  if alive else 0.0),
            }


# ═══ 全局单例 ══════════════════════════════════════════════

_ecosystem_instance: Optional[PairEcosystem] = None
_ecosystem_lock = threading.Lock()


def get_ecosystem() -> PairEcosystem:
    """获取对子协作生态全局单例"""
    global _ecosystem_instance
    if _ecosystem_instance is None:
        with _ecosystem_lock:
            if _ecosystem_instance is None:
                _ecosystem_instance = PairEcosystem()
    return _ecosystem_instance
