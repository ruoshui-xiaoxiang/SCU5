# -*- coding: utf-8 -*-
"""
api/pair.py — 单元对系统 API 路由
==================================
提供对子生态的状态查询、手动操作和经验回收接口。

路由：
  GET  /upair/status           — 对子生态系统状态
  GET  /upair/list             — 存活对子列表
  POST /upair/spawn            — 手动诞生新对子
  POST /upair/collect          — 手动回收死亡对子经验
  POST /upair/synergy          — 手动触发协同融合
  POST /upair/dispatch         — 分工协作调度
"""
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from api.deps import verify_api_key

logger = logging.getLogger("SCU3.api.pair")

router = APIRouter(tags=["pair"])


class SpawnRequest(BaseModel):
    specialty: str = "general"
    initial_energy: float = 1000.0


class SynergyRequest(BaseModel):
    pair_ids: List[str]


class DispatchSubtask(BaseModel):
    subtask: str
    specialty: str = "general"


class DispatchRequest(BaseModel):
    subtasks: List[DispatchSubtask]


@router.get("/upair/status")
async def pair_status(api_key: str = Depends(verify_api_key)):
    """对子生态系统状态"""
    from m_layer.evolution.pair_integration import pair_system_status
    return JSONResponse({"success": True, "data": pair_system_status()})


@router.get("/upair/list")
async def pair_list(api_key: str = Depends(verify_api_key)):
    """存活对子列表"""
    from m_layer.evolution.unit_pair import get_ecosystem
    ecosystem = get_ecosystem()
    alive = ecosystem.get_alive_pairs()
    return JSONResponse({"success": True, "data": {
        "count": len(alive),
        "pairs": [p.to_dict() for p in alive],
    }})


@router.post("/upair/spawn")
async def pair_spawn(req: SpawnRequest,
                     api_key: str = Depends(verify_api_key)):
    """手动诞生新对子"""
    from m_layer.evolution.unit_pair import get_ecosystem
    ecosystem = get_ecosystem()
    pair = ecosystem.spawn_pair(req.specialty, req.initial_energy)
    return JSONResponse({"success": True, "data": {
        "pair_id": pair.pair_id,
        "state": pair.to_dict(),
    }})


@router.post("/upair/collect")
async def pair_collect(api_key: str = Depends(verify_api_key)):
    """手动回收死亡对子经验"""
    from m_layer.evolution.pair_integration import collect_dead_pairs
    result = collect_dead_pairs()
    return JSONResponse({"success": True, "data": result})


@router.post("/upair/synergy")
async def pair_synergy(req: SynergyRequest,
                       api_key: str = Depends(verify_api_key)):
    """手动触发协同融合"""
    from m_layer.evolution.unit_pair import get_ecosystem
    ecosystem = get_ecosystem()
    ok, msg, replenish = ecosystem.synergy_fusion(req.pair_ids)
    return JSONResponse({"success": ok, "data": {
        "message": msg,
        "replenish": round(replenish, 2),
    }})


@router.post("/upair/dispatch")
async def pair_dispatch(req: DispatchRequest,
                        api_key: str = Depends(verify_api_key)):
    """分工协作调度"""
    from m_layer.evolution.pair_integration import dispatch_collaborative_task
    result = dispatch_collaborative_task(
        [st.dict() for st in req.subtasks]
    )
    return JSONResponse({"success": True, "data": result})
