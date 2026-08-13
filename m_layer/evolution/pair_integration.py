# -*- coding: utf-8 -*-
"""
m_layer/evolution/pair_integration.py — 单元对系统集成适配器
==============================================================
将 UnitPair 生命周期系统接入现有 SCU5 架构，作为可选层运行。

接入点：
  1. 工具执行时：通过 charge_operation() 从对子势能池扣税
  2. 阴阳对子思考：通过 register_callback() 注入 cognition._yin_yang_think
  3. 经验回收：通过 collect_dead_pairs() 将轨迹存入 experience_store + 知识库
  4. 多任务调度：通过 dispatch_collaborative_task() 分工协作

设计原则：
  - 不修改现有代码（ledger_runtime/cognition/experience_store 保持不变）
  - 作为可选层，可通过环境变量 SCU5_PAIR_ENABLED=1 启用
  - 失败时降级到原有逻辑，不影响系统运行
"""
import os
import sys
import logging
from typing import Dict, Any, Optional, Callable, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from m_layer.evolution.unit_pair import (
    UnitPair, PairEcosystem, get_ecosystem,
)

logger = logging.getLogger("SCU3.m.pair_integration")

# 是否启用对子系统（默认启用）
PAIR_ENABLED = os.environ.get("SCU5_PAIR_ENABLED", "1") != "0"

# 阴操作类型（消耗阴势能→转阳）
YIN_OPERATIONS = {"check", "inspect", "read", "query", "search", "crawl"}
# 阳操作类型（消耗阳势能→转阴）
YANG_OPERATIONS = {"write", "modify", "tool_call", "self_modify", "create", "generate"}


def get_pair_for_specialty(specialty: str) -> Optional[UnitPair]:
    """获取指定专长的对子（如果对子系统启用）"""
    if not PAIR_ENABLED:
        return None
    try:
        ecosystem = get_ecosystem()
        return ecosystem.get_best_pair_for_task(specialty)
    except Exception as e:
        logger.debug(f"获取对子失败: {e}")
        return None


def charge_operation(operation: str, cost: float,
                     specialty: str = "general",
                     reason: str = "",
                     callback_context: Optional[Dict] = None) -> Dict[str, Any]:
    """从对子势能池扣税

    阴操作消耗阴势能→转阳（阴降阳升）
    阳操作消耗阳势能→转阴（阳降阴升）

    Returns:
        {charged: bool, pair_id: str, bias: float, alive: bool, degraded: bool}
        degraded=True 表示降级到全局账本（对子系统未启用或失败）
    """
    if not PAIR_ENABLED:
        return {"charged": False, "degraded": True, "reason": "对子系统未启用"}

    try:
        pair = get_pair_for_specialty(specialty)
        if pair is None:
            return {"charged": False, "degraded": True, "reason": "无可用对子"}

        # 方案2：注入回调上下文（供 _do_callback 执行双签）
        if callback_context:
            pair.callback_context = callback_context

        if operation in YIN_OPERATIONS:
            ok, msg = pair.execute_yin_op(cost, reason)
        elif operation in YANG_OPERATIONS:
            ok, msg = pair.execute_yang_op(cost, reason)
        else:
            # 未知操作类型，按阳操作处理
            ok, msg = pair.execute_yang_op(cost, reason)

        # 方案2：回调由 cognition 层同步双签处理（不在此异步调度）
        # needs_callback 标志会透传到 cognition.process，触发 _yin_yang_think
        # 双签融合即是对子的中和回调，无需后台重复执行
        result = {
            "charged": ok,
            "pair_id": pair.pair_id,
            "bias": round(pair.tracker.bias(), 4),
            "stability": round(pair.tracker.stability(), 4),
            "energy": round(pair.tracker.e_total, 2),
            "alive": pair.is_alive,
            "needs_callback": pair.tracker.needs_callback(),
            "callback_triggered": pair.last_callback_response is not None,
            "callback_response": pair.last_callback_response,
            "callback_scheduled": pair.tracker.needs_callback() and pair.is_alive,
            "message": msg,
            "degraded": False,
        }
        # 清除已读取的回调回复，避免下次对话复用旧回复
        pair.last_callback_response = None
        return result
    except Exception as e:
        logger.warning(f"对子扣税异常，降级: {e}")
        return {"charged": False, "degraded": True, "reason": str(e)}


# ─── 回调注入 ────────────────────────────────────

_callback_handler: Optional[Callable] = None


def register_callback(handler: Callable) -> None:
    """注册回调处理器（由 cognition._yin_yang_think 注入）

    handler 签名: (pair: UnitPair, context: str) -> Tuple[bool, float, float]
    返回: (success, gamma_yin, gamma_yang)
    """
    global _callback_handler
    _callback_handler = handler
    logger.info("对子回调处理器已注册")


def inject_callback_to_pair(pair: UnitPair) -> None:
    """将对子的 _do_callback 替换为注册的回调处理器"""
    if _callback_handler is None:
        return

    original_callback = pair._do_callback

    def injected_callback():
        try:
            result = _callback_handler(pair, pair.task_context or "")
            if isinstance(result, tuple):
                success, gamma_yin, gamma_yang = result
                pair.record_gamma(gamma_yin, gamma_yang)
                return success
            return bool(result)
        except Exception as e:
            logger.warning(f"回调处理器异常: {e}")
            return original_callback()

    pair._do_callback = injected_callback


# ─── 经验回收 ────────────────────────────────────

def collect_dead_pairs() -> Dict[str, Any]:
    """回收死亡对子经验→experience_store + 知识库

    Returns:
        {collected: int, stored_experience: int, stored_knowledge: int}
    """
    if not PAIR_ENABLED:
        return {"collected": 0, "reason": "对子系统未启用"}

    try:
        ecosystem = get_ecosystem()
        experiences = ecosystem.collect_dead_experiences()

        if not experiences:
            return {"collected": 0}

        # 通道1：存入 experience_store
        stored_exp = 0
        try:
            from m_layer.evolution.experience_store import get_experience_store
            store = get_experience_store()
            for exp in experiences:
                # 将对子死亡轨迹存为失败经验
                pattern = exp.get("task_context", "")[:50] or "unknown"
                store.record_failure(
                    user_input=pattern,
                    plugin_name=f"pair_{exp.get('specialty', 'general')}",
                    tool_name="unit_pair",
                )
                stored_exp += 1
        except Exception as e:
            logger.warning(f"经验存入experience_store失败: {e}")

        # 通道2：存入公共知识库
        stored_kb = 0
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
            from w1_layer.knowledge_runtime import get_knowledge_store
            kb = get_knowledge_store()
            for exp in experiences:
                doc_text = _format_pair_trajectory(exp)
                kb.add_document(
                    text=doc_text,
                    metadata={
                        "source": "unit_pair_death",
                        "pair_id": exp.get("pair_id", ""),
                        "specialty": exp.get("specialty", ""),
                        "death_reason": exp.get("death_reason", ""),
                        "type": "pair_experience",
                    },
                )
                stored_kb += 1
        except Exception as e:
            logger.warning(f"经验存入知识库失败: {e}")

        logger.info(f"回收 {len(experiences)} 个死亡对子: "
                    f"experience_store={stored_exp}, knowledge_base={stored_kb}")
        return {
            "collected": len(experiences),
            "stored_experience": stored_exp,
            "stored_knowledge": stored_kb,
        }
    except Exception as e:
        logger.error(f"经验回收异常: {e}")
        return {"collected": 0, "error": str(e)}


def _format_pair_trajectory(exp: Dict) -> str:
    """格式化对子轨迹为知识库文档"""
    lines = [
        f"单元对死亡轨迹记录",
        f"对子ID: {exp.get('pair_id', 'unknown')}",
        f"专长: {exp.get('specialty', 'general')}",
        f"诞生: {exp.get('born_at', '')}",
        f"死亡: {exp.get('died_at', '')}",
        f"死因: {exp.get('death_reason', '')}",
        f"回调尝试次数: {exp.get('callback_attempts', 0)}",
        f"最终偏度: {exp.get('final_bias', 0):.4f}",
        f"最终势能: {exp.get('final_energy', 0):.2f}E",
        f"任务上下文: {exp.get('task_context', '')}",
        "",
        "操作轨迹:",
    ]
    for i, traj in enumerate(exp.get("trajectory", [])[:20]):
        lines.append(f"  {i+1}. [{traj.get('type', '')}] "
                     f"cost={traj.get('cost', 0):.2f} "
                     f"bias_after={traj.get('bias_after', 0):.4f} "
                     f"reason={traj.get('reason', '')}")

    gamma_hist = exp.get("gamma_history", [])
    if gamma_hist:
        lines.append("")
        lines.append("γ质量历史:")
        for g in gamma_hist[-10:]:
            lines.append(f"  γ_yin={g.get('gamma_yin', 0):.3f} "
                         f"γ_yang={g.get('gamma_yang', 0):.3f} "
                         f"bias={g.get('bias', 0):.4f}")

    lines.append("")
    lines.append("教训: 此对子因偏度过大且无法回调而死亡。"
                 "未来对子应避免相同的偏度累积模式。")
    return "\n".join(lines)


# ─── 多任务分工协作 ────────────────────────────────

def dispatch_collaborative_task(subtasks: List[Dict[str, str]]) -> Dict[str, Any]:
    """多任务分工协作

    Args:
        subtasks: [{subtask: "任务内容", specialty: "search/analysis/writing/coding"}]

    Returns:
        {results: [...], synergy: {...}, summary: str}
    """
    if not PAIR_ENABLED:
        return {"degraded": True, "reason": "对子系统未启用"}

    try:
        ecosystem = get_ecosystem()
        results = []
        pair_ids = []

        for st in subtasks:
            specialty = st.get("specialty", "general")
            task = st.get("subtask", "")
            pair = ecosystem.get_best_pair_for_task(specialty)
            inject_callback_to_pair(pair)
            pair.task_context = task

            # 执行任务（这里只记录，实际执行由调用方处理）
            results.append({
                "pair_id": pair.pair_id,
                "specialty": specialty,
                "task": task,
                "pair_state": pair.to_dict(),
            })
            pair_ids.append(pair.pair_id)

        # 协同融合
        synergy = {"attempted": False}
        if len(pair_ids) >= 2:
            ok, msg, replenish = ecosystem.synergy_fusion(pair_ids)
            synergy = {
                "attempted": True,
                "success": ok,
                "message": msg,
                "replenish": round(replenish, 2),
            }

        # 自动势能借贷
        lend_count = ecosystem.auto_lending()

        return {
            "results": results,
            "synergy": synergy,
            "lending_count": lend_count,
            "summary": f"分工协作完成: {len(results)}个对子, "
                       f"融合{'成功' if synergy.get('success') else '未尝试/失败'}, "
                       f"借贷{lend_count}次",
        }
    except Exception as e:
        logger.error(f"分工协作异常: {e}")
        return {"error": str(e), "degraded": True}


# ─── 状态查询 ────────────────────────────────────

def pair_system_status() -> Dict[str, Any]:
    """对子系统状态"""
    if not PAIR_ENABLED:
        return {"enabled": False}

    try:
        ecosystem = get_ecosystem()
        status = ecosystem.status()
        status["enabled"] = True
        status["callback_registered"] = _callback_handler is not None
        return status
    except Exception as e:
        return {"enabled": True, "error": str(e)}
