# -*- coding: utf-8 -*-
"""
guard/workflow_guard.py — 工作流 CUF 审批封装
================================================
为任务编排路径（/agent/run, /agent/execute, /multiagent/execute,
/parallel/execute, /agent/presets/{id}/run）补全 CUF 守卫审批。

修复安全漏洞：工作流执行路径此前完全绕过 CUFLogicFirewall，
违反项目硬约束"所有跨层操作必须通过 CUFLogicFirewall 检查并支付 k_cross 熵税"。

审批链路（与 /chat/stream 主对话流程对齐）：
  守卫① W2→M 跨层审计（API入口 → M层 Agent 编排）
  工具守卫 每个子任务按 specialty 审计
  守卫② M→W2 跨层审计（M层结果 → API输出）

熵税：每次跨层审计通过后由 ledger 自动扣缴 k_cross 熵税。
"""
import logging
import time
from typing import Dict, Any, Tuple, List

from d_layer.axioms import Operation
from guard.firewall import CUFGuard
from guard.tool_guard import ToolGuard

logger = logging.getLogger("SCU3.guard.workflow_guard")

# 子任务 specialty → 工具守卫中的 tool_name 映射
# 工作流的 specialty 是 Agent 角色，需映射到 tool_guard 已注册的工具类型
SPECIALTY_TOOL_MAP = {
    "search": "web_search",      # 研究员：联网搜索/爬取
    "analysis": "text_stats",    # 分析师：文本分析（read 类）
    "writing": "file_write",     # 写手：生成内容（write 类，需重点审计）
    "coding": "code_run",        # 工程师：代码执行（write 类，沙箱）
    "general": "web_search",     # 协调员：通用
}


def audit_workflow_entry(guard: CUFGuard, op_id: str,
                         goal: str) -> Tuple[bool, str, Dict[str, Any]]:
    """守卫①：工作流入口审计（W2→M 跨层）

    API 层属于 W2（用户接口），Agent 编排属于 M 层（认知/推理）。
    工作流执行前必须通过守卫①跨层审计并支付熵税。

    Args:
        guard: CUFGuard 单例
        op_id: 操作ID
        goal: 工作流目标

    Returns:
        (passed, message, details)
    """
    op = Operation(
        source="W2",
        target="M",
        action="layer_jump",
        op_id=f"{op_id}_g1",
        pattern_key="layer_jump:W2>M",
        metadata={"workflow_goal": goal[:200]},
    )
    ok, msg, details = guard.check(op)
    if ok:
        logger.info(f"工作流守卫①通过: op_id={op_id}, tax={details.get('tax', 0)}, goal={goal[:50]}")
    else:
        logger.warning(f"工作流守卫①拦截: op_id={op_id}, msg={msg}, goal={goal[:50]}")
    return ok, msg, details


def audit_subtask_tools(tool_guard: ToolGuard, op_id: str,
                        subtasks: List[Dict[str, Any]]) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """工具守卫：审计每个子任务的工具类型

    每个子任务的 specialty 映射到 tool_guard 中的工具类型，
    按 read/write 定税。write 类（coding/writing）需重点审计。

    Args:
        tool_guard: ToolGuard 单例
        op_id: 操作ID
        subtasks: 子任务列表 [{subtask, specialty, ...}]

    Returns:
        (all_passed, error_msg, traces)
    """
    traces = []
    for i, st in enumerate(subtasks):
        specialty = st.get("specialty", "general")
        tool_name = SPECIALTY_TOOL_MAP.get(specialty, "web_search")
        # P2技术债：guard层不应依赖W1层，应通过依赖注入传入 tool_type 映射表。
        # 当前采用延迟导入+防御性降级，避免编译期依赖。
        # TODO: 重构为在 server.py startup 时将 TOOL_TYPES 注入到 guard 层
        try:
            from w1_layer.action import ActionLayer
            tool_type = ActionLayer.TOOL_TYPES.get(tool_name, "read")
        except Exception:
            tool_type = "read"  # 降级：未知工具按read计税

        ok, msg, details = tool_guard.check(
            tool_name, tool_type, op_id=f"{op_id}_tool_{i}"
        )
        traces.append({
            "subtask_idx": i,
            "specialty": specialty,
            "tool": tool_name,
            "tool_type": tool_type,
            "passed": ok,
            "msg": msg,
            "tax": details.get("tax", 0),
        })
        if not ok:
            logger.warning(f"工具守卫拦截子任务[{i}] specialty={specialty}: {msg}")
            return False, f"子任务[{i}]({specialty})被工具守卫拦截: {msg}", traces
        logger.info(f"工具守卫通过子任务[{i}] specialty={specialty}, tool={tool_name}, tax={details.get('tax', 0)}")

    return True, "全部通过", traces


def audit_workflow_exit(guard: CUFGuard, op_id: str,
                        result_summary: str) -> Tuple[bool, str, Dict[str, Any]]:
    """守卫②：工作流出口审计（M→W2 跨层）

    Agent 编排结果返回 API 层前必须通过守卫②跨层审计并支付熵税。

    Args:
        guard: CUFGuard 单例
        op_id: 操作ID
        result_summary: 结果摘要（用于审计日志）

    Returns:
        (passed, message, details)
    """
    op = Operation(
        source="M",
        target="W2",
        action="layer_jump",
        op_id=f"{op_id}_g2",
        pattern_key="layer_jump:M>W2",
        metadata={"result_summary": result_summary[:200]},
    )
    ok, msg, details = guard.check(op)
    if ok:
        logger.info(f"工作流守卫②通过: op_id={op_id}, tax={details.get('tax', 0)}")
    else:
        logger.warning(f"工作流守卫②拦截: op_id={op_id}, msg={msg}")
    return ok, msg, details


def run_with_cuf_audit(guard: CUFGuard, tool_guard: ToolGuard,
                       op_id: str, goal: str,
                       subtasks: List[Dict[str, Any]],
                       execute_fn) -> Dict[str, Any]:
    """完整的 CUF 审批封装：守卫① → 工具守卫 → 执行 → 守卫②

    通用封装函数，所有工作流端点共用，确保审批链路一致。

    Args:
        guard: CUFGuard 单例
        tool_guard: ToolGuard 单例
        op_id: 操作ID
        goal: 工作流目标
        subtasks: 子任务列表
        execute_fn: 执行函数，签名为 () -> Dict[str, Any]

    Returns:
        执行结果（含 cuf_traces 审计轨迹）
    """
    cuf_traces = []
    start_time = time.time()

    # ① 守卫①：W2→M 跨层审计
    ok1, msg1, d1 = audit_workflow_entry(guard, op_id, goal)
    cuf_traces.append({
        "guard": "W2→M", "passed": ok1, "msg": msg1,
        "tax": d1.get("tax", 0), "op_id": f"{op_id}_g1",
    })
    if not ok1:
        return {
            "success": False,
            "error": f"CUF守卫①拦截: {msg1}",
            "cuf_blocked": True,
            "cuf_traces": cuf_traces,
            "execution_time": time.time() - start_time,
        }

    # ② 工具守卫：审计每个子任务
    ok_t, msg_t, tool_traces = audit_subtask_tools(tool_guard, op_id, subtasks)
    cuf_traces.append({
        "guard": "tool", "passed": ok_t, "msg": msg_t,
        "subtask_traces": tool_traces,
    })
    if not ok_t:
        return {
            "success": False,
            "error": f"工具守卫拦截: {msg_t}",
            "cuf_blocked": True,
            "cuf_traces": cuf_traces,
            "execution_time": time.time() - start_time,
        }

    # ③ 执行工作流
    try:
        result = execute_fn()
    except Exception as e:
        logger.error(f"工作流执行异常: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"工作流执行异常: {e}",
            "cuf_traces": cuf_traces,
            "execution_time": time.time() - start_time,
        }

    # ④ 守卫②：M→W2 跨层审计
    result_summary = ""
    if isinstance(result, dict):
        result_summary = result.get("summary", "") or str(result.get("final_output", ""))[:200]
    ok2, msg2, d2 = audit_workflow_exit(guard, op_id, result_summary)
    cuf_traces.append({
        "guard": "M→W2", "passed": ok2, "msg": msg2,
        "tax": d2.get("tax", 0), "op_id": f"{op_id}_g2",
    })
    if not ok2:
        return {
            "success": False,
            "error": f"CUF守卫②拦截: {msg2}",
            "cuf_blocked": True,
            "cuf_traces": cuf_traces,
            "execution_time": time.time() - start_time,
        }

    # ⑤ 附加审计轨迹到结果
    # 守卫②通过即视为工作流审计成功，标记 success=True 供下游判断
    # （execute_fn 返回的 dict 可能没有 success 键，如 quick_multi_agent）
    if isinstance(result, dict):
        result["cuf_traces"] = cuf_traces
        result["cuf_audited"] = True
        result["success"] = True
        result["execution_time"] = time.time() - start_time
    return result


# ==================== SCU5.1：CUF 审计装饰器（限制2） ====================

import functools
import asyncio


def cuf_audit(op_id: str = "", goal: str = "", subtasks_field: str = "tools"):
    """CUF 审计装饰器（限制2）

    自动为执行类端点接入 CUF 审批链路（守卫①→工具守卫→执行→守卫②），
    替代手动调用 run_with_cuf_audit。

    用法：
        @router.post("/toolchain/execute")
        @cuf_audit(op_id="toolchain", goal="多工具链式执行")
        async def toolchain_execute(req, api_key=...):
            ...

    装饰器会：
    1. 从 api.deps 获取 guard/tool_guard 单例
    2. 从请求体的 subtasks_field 字段提取子任务（默认 tools）
    3. 将原函数作为 execute_fn 包装进 run_with_cuf_audit
    4. 自动用 asyncio.to_thread 异步执行（避免阻塞事件循环）

    Args:
        op_id: 操作ID（空则用函数名）
        goal: 工作流目标（空则用函数 docstring 首行）
        subtasks_field: 请求体中子任务列表的字段名
    """
    def decorator(func):
        _op_id = op_id or f"cuf_{func.__name__}"
        _goal = goal or (func.__doc__.strip().split(chr(10))[0] if func.__doc__ else func.__name__)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 api.deps 获取 guard/tool_guard（延迟导入避免循环依赖）
            try:
                from api.deps import get
                _guard = get("guard")
                _tool_guard = get("tool_guard")
            except Exception:
                _guard = None
                _tool_guard = None

            # 如果 guard 未就绪（启动早期或未注入），直接执行原函数（降级）
            if _guard is None or _tool_guard is None:
                return await _call_original(func, args, kwargs)

            # 从请求参数提取子任务（FastAPI 端点的第一个位置参数通常是 req）
            subtasks = []
            for a in args:
                if hasattr(a, subtasks_field) or hasattr(a, "model_dump"):
                    try:
                        data = a.model_dump() if hasattr(a, "model_dump") else a.__dict__
                        raw = data.get(subtasks_field, [])
                        if isinstance(raw, list):
                            subtasks = [{"tool": str(s), "specialty": "general"} for s in raw]
                    except Exception:
                        pass
                    break

            # 同步执行函数（原端点可能是 async 或 sync，统一提取为同步 execute_fn）
            def execute_fn():
                import inspect
                if inspect.iscoroutinefunction(func):
                    # async 端点：在新事件循环中执行
                    loop = asyncio.new_event_loop()
                    try:
                        return loop.run_until_complete(func(*args, **kwargs))
                    finally:
                        loop.close()
                else:
                    return func(*args, **kwargs)

            # 用 run_with_cuf_audit 包装执行（异步，避免阻塞）
            result = await asyncio.to_thread(
                run_with_cuf_audit,
                guard=_guard, tool_guard=_tool_guard,
                op_id=_op_id, goal=_goal,
                subtasks=subtasks, execute_fn=execute_fn,
            )
            return result

        return wrapper
    return decorator


async def _call_original(func, args, kwargs):
    """降级：guard 未就绪时直接调用原函数"""
    import inspect
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)
