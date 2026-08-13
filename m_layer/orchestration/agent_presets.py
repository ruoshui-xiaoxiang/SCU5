# -*- coding: utf-8 -*-
"""
预置 Agent 工作流
==================
基于 TRAE AI 助手的工作模式，抽象为 5 种 Agent 角色 + 6 个实用预置工作流。

角色映射：
  研究员 (search)    → 联网搜索、爬取、知识检索
  分析师 (analysis)  → 深度分析、批判思考、对比
  写手   (writing)   → 生成报告、文案、文档
  工程师 (coding)    → 写代码、调试、重构
  协调员 (general)   → 任务拆解、流程编排

调用方式：
  POST /multiagent/execute
  body: { "mode": "thread", "subtasks": [...] }
"""
import os
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger("SCU3.m.agent_presets")

# ─── 预置工作流定义 ──────────────────────────────────
# 每个工作流包含: id, name, description, mode, goal_template, subtasks
# goal_template 中的 {topic} 占位符在调用时被用户输入替换

PRESETS: List[Dict[str, Any]] = [
    {
        "id": "research_report",
        "name": "深度研究报告",
        "description": "研究员搜集资料 → 分析师提炼洞察 → 写手生成结构化报告",
        "icon": "📋",
        "mode": "thread",
        "goal_template": "针对主题「{topic}」生成深度研究报告",
        "subtasks": [
            {
                "subtask": "联网搜索「{topic}」的最新资讯、权威来源、关键数据，汇总成资料卡",
                "specialty": "search"
            },
            {
                "subtask": "基于研究资料，提炼3-5个核心洞察，对比不同观点，指出争议点和共识",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "综合洞察生成结构化报告：背景、核心观点、数据支撑、结论与建议",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "code_solution",
        "name": "代码方案生成",
        "description": "研究员调研最佳实践 → 工程师实现代码 → 分析师审查质量",
        "icon": "💻",
        "mode": "thread",
        "goal_template": "针对需求「{topic}」生成完整代码方案",
        "subtasks": [
            {
                "subtask": "搜索「{topic}」的主流实现方案、开源库、最佳实践，对比优劣",
                "specialty": "search"
            },
            {
                "subtask": "基于调研结果，编写完整可运行的代码方案，包含核心实现、接口设计、错误处理",
                "specialty": "coding",
                "depends_on": ["t1"]
            },
            {
                "subtask": "审查代码方案的：安全性、性能、可维护性、边界情况，给出改进建议",
                "specialty": "analysis",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "decision_analysis",
        "name": "决策分析",
        "description": "研究员搜集信息 → 分析师利弊分析 → 写手输出决策建议",
        "icon": "⚖️",
        "mode": "thread",
        "goal_template": "针对决策「{topic}」提供深度分析建议",
        "subtasks": [
            {
                "subtask": "搜集「{topic}」的背景信息、相关案例、利益相关方观点",
                "specialty": "search"
            },
            {
                "subtask": "进行利弊分析：列出3个支持理由、3个反对理由、潜在风险、机会成本",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出决策建议书：情境分析、选项对比、推荐方案、实施要点",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "content_creation",
        "name": "内容创作",
        "description": "研究员搜集素材 → 写手生成初稿 → 分析师优化润色",
        "icon": "✍️",
        "mode": "thread",
        "goal_template": "围绕主题「{topic}」创作高质量内容",
        "subtasks": [
            {
                "subtask": "搜集「{topic}」的热点角度、受众痛点、爆款案例、关键词",
                "specialty": "search"
            },
            {
                "subtask": "基于素材创作内容：吸引人的标题、清晰的结构、有价值的观点、行动号召",
                "specialty": "writing",
                "depends_on": ["t1"]
            },
            {
                "subtask": "优化内容：逻辑连贯性、表达感染力、可读性、传播性，提出修改建议",
                "specialty": "analysis",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "bug_investigation",
        "name": "Bug 排查",
        "description": "研究员搜索类似问题 → 工程师定位根因 → 分析师输出修复方案",
        "icon": "🐛",
        "mode": "thread",
        "goal_template": "排查并解决 Bug：「{topic}」",
        "subtasks": [
            {
                "subtask": "搜索「{topic}」相关的已知问题、Stack Overflow 讨论、官方文档说明",
                "specialty": "search"
            },
            {
                "subtask": "分析可能的根因：代码逻辑、依赖冲突、环境配置、数据问题，给出排查步骤",
                "specialty": "coding",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出修复方案：根因分析、修复步骤、验证方法、预防措施",
                "specialty": "analysis",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "learning_path",
        "name": "学习路径规划",
        "description": "研究员搜集学习资源 → 分析师评估路径 → 写手生成学习计划",
        "icon": "📚",
        "mode": "thread",
        "goal_template": "为主题「{topic}」规划系统学习路径",
        "subtasks": [
            {
                "subtask": "搜集「{topic}」的优质学习资源：书籍、课程、文档、社区、实战项目",
                "specialty": "search"
            },
            {
                "subtask": "评估学习路径：前置知识、核心概念、进阶方向、常见误区、时间预估",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "生成学习计划：分阶段目标、每周任务、推荐资源、检验标准、里程碑",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    }    ,
    {
        "id": "product_prd",
        "name": "产品需求文档",
        "description": "研究员调研市场→分析师提炼需求→写手生成PRD文档",
        "icon": "📝",
        "mode": "thread",
        "goal_template": "为产品「{topic}」生成完整的产品需求文档(PRD)",
        "subtasks": [
            {
                "subtask": "调研「{topic}」的市场现状、目标用户、竞品功能、用户痛点",
                "specialty": "search"
            },
            {
                "subtask": "基于调研提炼核心需求：功能列表、优先级、用户故事、验收标准",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "生成结构化PRD：背景目标、功能详述、交互流程、数据指标、风险项",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "project_plan",
        "name": "项目方案规划",
        "description": "协调员拆解任务→工程师评估技术→写手输出项目计划",
        "icon": "📊",
        "mode": "thread",
        "goal_template": "为项目「{topic}」制定完整实施方案",
        "subtasks": [
            {
                "subtask": "拆解「{topic}」的项目目标、关键里程碑、风险点、资源需求",
                "specialty": "general"
            },
            {
                "subtask": "评估技术方案：架构选型、技术栈、难点攻关、工期预估",
                "specialty": "coding",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出项目计划书：目标范围、WBS拆解、排期表、风险预案、验收标准",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "data_analysis",
        "name": "数据分析报告",
        "description": "研究员收集数据→分析师建模分析→写手生成分析报告",
        "icon": "📈",
        "mode": "thread",
        "goal_template": "对「{topic}」进行深度数据分析并生成报告",
        "subtasks": [
            {
                "subtask": "收集「{topic}」的相关数据来源、关键指标、行业基准、数据获取方式",
                "specialty": "search"
            },
            {
                "subtask": "设计分析框架：指标体系、分析方法、对比维度、可视化方案",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "生成数据分析报告：数据概览、核心发现、趋势预测、决策建议",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "security_audit",
        "name": "安全审计",
        "description": "工程师扫描漏洞→分析师评估风险→写手输出审计报告",
        "icon": "🛡️",
        "mode": "thread",
        "goal_template": "对「{topic}」进行安全审计并生成报告",
        "subtasks": [
            {
                "subtask": "扫描「{topic}」的安全风险：注入、XSS、CSRF、越权、敏感信息泄露、依赖漏洞",
                "specialty": "coding"
            },
            {
                "subtask": "评估风险等级：CVSS评分、影响范围、利用难度、修复优先级",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出安全审计报告：漏洞清单、风险矩阵、修复方案、加固建议",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "test_plan",
        "name": "测试方案设计",
        "description": "分析师梳理用例→工程师设计自动化→写手生成测试文档",
        "icon": "🧪",
        "mode": "thread",
        "goal_template": "为「{topic}」设计完整的测试方案",
        "subtasks": [
            {
                "subtask": "梳理「{topic}」的测试范围、功能点、边界条件、异常场景",
                "specialty": "analysis"
            },
            {
                "subtask": "设计自动化测试方案：用例分层、框架选型、CI集成、覆盖率目标",
                "specialty": "coding",
                "depends_on": ["t1"]
            },
            {
                "subtask": "生成测试文档：测试计划、用例清单、执行步骤、准入准出标准",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "translation_review",
        "name": "翻译与审校",
        "description": "写手初译→分析师校对→写手润色定稿",
        "icon": "🌐",
        "mode": "thread",
        "goal_template": "翻译并审校「{topic}」",
        "subtasks": [
            {
                "subtask": "对「{topic}」进行初译：忠于原文、术语统一、句式自然",
                "specialty": "writing"
            },
            {
                "subtask": "校对译文：准确性、完整性、术语一致性、文化适配、语法错误",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "润色定稿：提升流畅度、优化表达、统一风格、生成译注",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "code_review",
        "name": "代码评审",
        "description": "工程师静态分析→分析师架构评估→写手输出评审报告",
        "icon": "🔍",
        "mode": "thread",
        "goal_template": "对代码「{topic}」进行深度评审",
        "subtasks": [
            {
                "subtask": "静态分析「{topic}」：命名规范、复杂度、重复代码、潜在bug、安全漏洞",
                "specialty": "coding"
            },
            {
                "subtask": "架构评估：模块耦合、扩展性、可测试性、设计模式使用、技术债",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出评审报告：问题清单(按严重度)、改进建议、重构方案、优先级排序",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    },
    {
        "id": "competitor_analysis",
        "name": "竞品分析",
        "description": "研究员搜集竞品→分析师对比矩阵→写手输出分析报告",
        "icon": "⚔️",
        "mode": "thread",
        "goal_template": "对「{topic}」进行竞品分析",
        "subtasks": [
            {
                "subtask": "搜集「{topic}」的主要竞品：功能特性、定价、用户规模、市场占有率、口碑",
                "specialty": "search"
            },
            {
                "subtask": "构建对比矩阵：功能对比、优劣势、差异化定位、威胁等级、机会点",
                "specialty": "analysis",
                "depends_on": ["t1"]
            },
            {
                "subtask": "输出竞品分析报告：市场格局、竞品画像、SWOT分析、战略建议",
                "specialty": "writing",
                "depends_on": ["t2"]
            }
        ]
    }
]


def list_presets() -> List[Dict[str, Any]]:
    """返回所有预置工作流（脱敏，不含 subtasks 详情）"""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "icon": p["icon"],
            "mode": p["mode"],
            "goal_template": p["goal_template"],
        }
        for p in PRESETS
    ]


def get_preset(preset_id: str) -> Dict[str, Any] | None:
    """获取指定预置工作流的完整定义"""
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None


def build_request(preset_id: str, topic: str) -> Dict[str, Any] | None:
    """根据预置工作流 + 用户输入主题，构建 /multiagent/execute 请求体

    Args:
        preset_id: 预置工作流ID
        topic: 用户输入的主题（如"GPT-5"、"用户登录Bug"）

    Returns:
        可直接 POST 到 /multiagent/execute 的请求体，或 None
    """
    preset = get_preset(preset_id)
    if not preset:
        return None

    # 替换 subtask 中的 {topic} 占位符
    subtasks = []
    for i, st in enumerate(preset["subtasks"], 1):
        task = {
            "subtask": st["subtask"].replace("{topic}", topic),
            "specialty": st.get("specialty", "general"),
        }
        if "depends_on" in st:
            task["depends_on"] = st["depends_on"]
        subtasks.append(task)

    return {
        "mode": preset["mode"],
        "goal": preset["goal_template"].replace("{topic}", topic),
        "subtasks": subtasks,
    }
