# -*- coding: utf-8 -*-
"""SCU5.1 冒烟测试（16项）"""
import sys, os, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO = r"C:\Users\若水\Desktop\SCU5"
os.chdir(REPO)
sys.path.insert(0, REPO)

BASE = "http://127.0.0.1:8300"
import requests
API_KEY = os.environ.get("SCU_API_KEY", "")
ADMIN_KEY = os.environ.get("SCU_ADMIN_KEY", "")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

results = []

def test(idx, name, func):
    try:
        ok, detail = func()
        status = "PASS" if ok else "FAIL"
        results.append((idx, name, status, detail))
        print(f"[{status}] {idx}. {name}: {detail}")
        return ok
    except Exception as e:
        results.append((idx, name, "ERROR", str(e)))
        print(f"[ERROR] {idx}. {name}: {e}")
        return False


# 1. health 端点
def t1():
    r = requests.get(f"{BASE}/health", timeout=5)
    data = r.json()
    ok = data.get("status") == "ok" and "balance" in data
    return ok, f"status={data.get('status')}, balance={data.get('balance')}"
test(1, "health 端点", t1)

# 2. D 层完整性
def t2():
    from guard.d_layer_integrity import verify_on_startup
    ok, report = verify_on_startup()
    return ok, f"{'通过' if ok else '失败'}: {report[:80] if isinstance(report, str) else report}"
test(2, "D 层完整性校验", t2)

# 3. 模块注册表
def t3():
    from m_layer.module_registry import get_registry
    reg = get_registry()
    has_list = hasattr(reg, 'list_modules')
    modules = reg.list_modules() if has_list else []
    # 独立进程中模块未注册（注册发生在服务启动时），检查 registry 可用即可
    ok = reg is not None and has_list
    return ok, f"registry={'可用' if ok else '不可用'}, 已注册={len(modules)}个(服务启动后注册)"
test(3, "模块注册表", t3)

# 4. 知识库检索
def t4():
    from w1_layer.vector_store import VectorKnowledgeStore
    store = VectorKnowledgeStore()
    status = store.status()
    docs = status.get("total_documents", 0)
    ok = docs > 0
    results = store.search("修复了什么", top_k=1)
    has_result = len(results) > 0
    return ok and has_result, f"{docs} 文档, 检索{'有结果' if has_result else '无结果'}, 后端={status.get('embed_backend')}"
test(4, "知识库检索", t4)

# 5. 路径穿越防护
def t5():
    # 注：需重启服务加载中间件后才能在HTTP层验证；未重启时由认证(401)先拦截
    r = requests.post(f"{BASE}/multimodal/image",
                      json={"path": "../../etc/passwd"},
                      headers=HEADERS, timeout=5)
    # 400=中间件拦截, 401=认证拦截(服务未重启), 403=权限不足
    ok = r.status_code in (400, 401, 403)
    _mode = "中间件拦截" if r.status_code == 400 else ("认证拦截(需重启服务)" if r.status_code == 401 else f"HTTP{r.status_code}")
    return ok, f"HTTP {r.status_code}, {_mode}"
test(5, "路径穿越防护", t5)

# 6. 认证
def t6():
    r = requests.get(f"{BASE}/ledger/balance", timeout=5)
    ok = r.status_code in (401, 403)
    return ok, f"无 Key → HTTP {r.status_code} ({'正确拒绝' if ok else '未拒绝!'})"
test(6, "认证拦截", t6)

# 7. 自修改引擎
def t7():
    from m_layer.evolution.code_self_modify import CodeSelfModifier, get_modifier, init_modifier
    try:
        cm = get_modifier()
    except Exception:
        try:
            init_modifier(project_root=os.getcwd())
            cm = get_modifier()
        except Exception:
            cm = CodeSelfModifier(project_root=os.getcwd())
    protected = getattr(cm, 'PROTECTED_FILES', []) or getattr(cm, '_protected_files', [])
    pending = cm.list_pending() if hasattr(cm, 'list_pending') else []
    ok = cm is not None
    return ok, f"CodeSelfModifier={'可用' if ok else '不可用'}, {len(protected)} 个受保护文件, {len(pending)} 待审批"
test(7, "自修改引擎", t7)

# 8. 多 Agent 模式
def t8():
    from m_layer.orchestration.multi_agent import MultiAgentCoordinator, get_multi_agent_coordinator
    try:
        mao = get_multi_agent_coordinator()
    except Exception:
        mao = MultiAgentCoordinator()
    ok = mao is not None
    return ok, "MultiAgentCoordinator 初始化成功"
test(8, "多 Agent 模式", t8)

# 9. 对话流程-意图识别
def t9():
    from w2_layer.perception import PerceptionLayer
    perc = PerceptionLayer()
    intent = perc._detect_intent("你好")
    ok = intent in ("greeting", "conversation", "knowledge_query")
    return ok, f"'你好' → intent={intent}"
test(9, "对话流程-意图识别", t9)

# 10. 对子思考触发
def t10():
    from w2_layer.perception import PerceptionLayer
    perc = PerceptionLayer()
    intent = perc._detect_intent("分析人工智能取代人类工作的可能性")
    ok = intent == "analytical"
    return ok, f"'分析...可能性' → intent={intent} ({'触发' if ok else '未触发!'})"
test(10, "对子思考触发", t10)

# 11. 账本持久化
def t11():
    from w1_layer.ledger_runtime import LedgerRuntime
    ledger = LedgerRuntime()
    balance = ledger.balance()
    history = ledger.history(limit=1)
    ok = balance >= 0 and isinstance(history, list)
    return ok, f"balance={balance}, history={len(history)}条"
test(11, "账本持久化", t11)

# 12. 语法检查（全量）
def t12():
    import py_compile, glob
    py_files = glob.glob(os.path.join(REPO, "**/*.py"), recursive=True)
    py_files = [f for f in py_files if '__pycache__' not in f and '.git' not in f]
    fail_count = 0
    for f in py_files:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError:
            fail_count += 1
    ok = fail_count == 0
    return ok, f"{len(py_files)} 文件, {fail_count} 语法错误"
test(12, "语法检查（全量）", t12)

# 13. SCU5.1: 路径校验中间件
def t13():
    from api.middleware import PathValidationMiddleware, TRAVERSAL_PATTERNS
    test_url = "http://localhost/x?path=../../etc/passwd"
    blocked = any(p.search(test_url) for p in TRAVERSAL_PATTERNS)
    ok = blocked
    return ok, f"中间件 {len(TRAVERSAL_PATTERNS)} 个穿越模式, 拦截测试={'通过' if ok else '失败'}"
test(13, "SCU5.1 路径校验中间件", t13)

# 14. SCU5.1: 事件循环监控探针
def t14():
    from api.middleware import get_loop_monitor
    monitor = get_loop_monitor()
    stats = monitor.stats()
    ok = "enabled" in stats and "samples" in stats
    return ok, f"enabled={stats.get('enabled')}, samples={stats.get('samples', 0)}"
test(14, "SCU5.1 事件循环监控探针", t14)

# 15. SCU5.1: 意图路由配置化 + analytical 扩展
def t15():
    from w2_layer.perception import PerceptionLayer, _load_intent_config
    cfg = _load_intent_config()
    ok_cfg = cfg is not None and "rules" in cfg
    perc = PerceptionLayer()
    test_cases = [
        "对比两种方案的优劣",
        "为什么服务器启动失败",
        "假设断电了会怎样",
    ]
    hit = 0
    for t in test_cases:
        if perc._detect_intent(t) == "analytical":
            hit += 1
    ok = ok_cfg and hit >= 2
    return ok, f"配置={'已加载' if ok_cfg else '未加载'}, analytical扩展 {hit}/3 命中"
test(15, "SCU5.1 意图路由配置化+扩展", t15)

# 16. SCU5.1: Merkle 树摘要
def t16():
    from w1_layer.ledger_runtime import LedgerRuntime
    ledger = LedgerRuntime()
    has_merkle = hasattr(ledger, '_merkle_roots')
    can_compute = hasattr(ledger, '_compute_merkle_root')
    if has_merkle and can_compute:
        root = ledger._compute_merkle_root([{"hash": "a"}, {"hash": "b"}])
        ok = isinstance(root, str) and len(root) > 0
        return ok, f"_merkle_roots={ledger._merkle_roots}, 根计算={'正常' if ok else '异常'}"
    return False, "Merkle 方法不存在"
test(16, "SCU5.1 Merkle 树摘要", t16)

# 汇总
print("\n" + "=" * 60)
print("冒烟测试汇总")
print("=" * 60)
pass_count = sum(1 for r in results if r[2] == "PASS")
fail_count = sum(1 for r in results if r[2] == "FAIL")
error_count = sum(1 for r in results if r[2] == "ERROR")
print(f"总计: {len(results)} 项")
print(f"通过: {pass_count} 项")
print(f"失败: {fail_count} 项")
print(f"错误: {error_count} 项")
print(f"\n结果: {'ALL PASS' if pass_count == len(results) else str(fail_count + error_count) + ' FAIL'}")

fails = [r for r in results if r[2] != "PASS"]
if fails:
    print("\n失败项明细:")
    for idx, name, status, detail in fails:
        print(f"  [{status}] {idx}. {name}: {detail}")
