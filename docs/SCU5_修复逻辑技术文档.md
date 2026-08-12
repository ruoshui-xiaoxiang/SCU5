# SCU5.0 修复逻辑技术文档

## 文档信息
- 版本：SCU5.0
- 日期：2026-08-12
- 作者：ruoshui-xiaoxiang

## 一、修复概览
本次修复涵盖P0（启动卡点+安全漏洞）、P1（并发安全+防护）、P2（架构违规+功能完善）共4个批次，以及2个遗留问题和1个对子思考触发问题。

## 二、P0修复：启动卡点与目录穿越

### 2.1 启动卡点（server.py）
- **问题**：`startup`钩子中同步调用`ledger.refund(0.0)`，该方法在持锁状态下触发`_save()`的文件IO+sleep重试，阻塞async事件循环导致服务卡死
- **修复**：移除`ledger.refund(0.0)`调用，改为只读校验：`balance()` + `history()` 验证账本可读，`os.access` 验证目录可写
- **关键代码**：
```python
# P0修复：移除 ledger.refund(0.0) 调用——它会在持锁状态下触发 _save()
# 的文件IO+sleep重试，阻塞 async 事件循环导致服务卡死。
# 改为只读校验：balance() + history() 验证账本可读，os.access 验证目录可写。
try:
    import os as _os
    test_bal = ledger.balance()
    test_hist = ledger.history(limit=1)
    store_dir = _os.path.dirname(ledger.store_path) or "."
    if not _os.path.isdir(store_dir):
        raise RuntimeError(f"账本目录不存在: {store_dir}")
    if not _os.access(store_dir, _os.W_OK):
        raise RuntimeError(f"账本目录不可写: {store_dir}")
    logger.info(f"账本就绪校验通过: 余额={test_bal:.2f}E, 历史记录={len(test_hist)}条, 目录可写")
except Exception as e:
    logger.error(f"⚠️ 账本就绪校验失败：{e}")
    app.state.ledger_ready = False
else:
    app.state.ledger_ready = True
```

### 2.2 目录穿越漏洞（3处）
- **api/vision.py**：`save_dir`未限制用户输入路径
- **api/plugins.py**：`/plugins/load`未限制加载路径
- **api/knowledge.py**：`/knowledge/import`未限制导入路径
- **修复**：新增`w1_layer/path_utils.py`的`safe_join_path`函数，通过`os.path.realpath`规范化路径并校验是否在指定基目录内

## 三、P1修复：并发安全与安全防护

### 3.1 账本并发安全（ledger_runtime.py）
- **问题**：`_replenish_timestamps`为类变量导致多实例共享状态
- **修复**：改为实例变量`self._replenish_timestamps = []`

### 3.2 API响应泄漏traceback（chat.py）
- **问题**：异常处理直接返回traceback给客户端，泄漏文件路径/库版本
- **修复**：生成error_id，traceback只记日志，客户端只收error_id

### 3.3 多Agent端点绕过CUF审计（agent.py）
- **问题**：`/multiagent/thread`、`/multiagent/process`、`/multiagent/mixed`直接执行不走审计
- **修复**：统一走`run_with_cuf_audit`封装的三阶段审计链

### 3.4 SSRF防护（browser.py）
- **问题**：`/browser/fetch`未限制目标URL，可访问内网
- **修复**：添加SSRF防护，拦截内网IP（private/loopback/link_local/reserved）、云元数据端点（169.254.169.254）、内网域名（.internal）

### 3.5 安全分数矛盾（code_self_modify.py）
- **问题**：文件写操作不影响score，导致passed=False但score=1.0
- **修复**：文件写操作每项扣0.1分，禁止项每项扣0.3分

### 3.6 D层契约校验穿透（contracts.py）
- **问题**：`validate_contract_detail`非dict结构时continue后最终返回True
- **修复**：非dict结构直接返回False

## 四、P2修复：架构违规与功能完善

### 4.1 L2语义记忆无持久化（l2_semantic.py）
- **问题**：L2语义记忆仅在内存，重启丢失
- **修复**：增加`_save()`和`_load()`方法，JSON持久化（原子写入：tempfile + os.replace）

### 4.2 哈希链截断说明（ledger_runtime.py）
- **问题**：仅持久化最近500条历史，哈希链防篡改能力对旧记录失效
- **修复**：添加注释说明权衡，TODO改为Merkle树

### 4.3 循环依赖（chat.py）
- **问题**：直接`from server import process_request`造成循环依赖
- **修复**：通过`deps.get("process_request")`获取，未注入时回退

## 五、遗留问题修复

### 5.1 账本JSON脏数据
- **问题**：`SCU3_data/ledger.json`末尾有"test"字符导致`Extra data`解析失败
- **修复**：
  1. 清理文件末尾脏数据
  2. `_load`方法增加容错：`json.JSONDecoder().raw_decode()`解析首个JSON对象，忽略尾部脏数据
  3. 编码改为`utf-8-sig`兼容BOM

### 5.2 同步阻塞事件循环（agent.py）
- **问题**：8个端点同步调用LLM，阻塞事件循环导致并发请求超时
- **修复**：用`asyncio.to_thread`包装所有同步调用
- **影响的端点**：`/multiagent/execute`、`/multiagent/thread`、`/multiagent/process`、`/multiagent/mixed`、`/agent/run`、`/agent/execute`、`/agent/presets/{id}/run`、`/parallel/execute`

## 六、对子思考触发修复（核心）

### 6.1 问题诊断
- **现象**：对子思考代码完整实现（阴方DeepSeek + 阳方Qwen + 太极合一），但无法触发
- **根因**：感知层`_detect_workflow_intent`的第三层LLM语义推理会拦截分析型问题，返回`workflow:research_report`，导致`analytical`意图检测永远无法执行

### 6.2 触发链路对比
修复前：
```
用户输入"分析人工智能取代人类工作的可能性"
  → _detect_workflow_intent() 第③层 LLM语义推理
  → LLM判定为 research_report 工作流
  → 返回 workflow:research_report（拦截了analytical路径）
  → analytical 意图检测无法执行
  → 对子思考无法触发
```

修复后：
```
用户输入"分析人工智能取代人类工作的可能性"
  → _detect_workflow_intent() 第②.5步 短路检查
  → 匹配"分析.*可能性"模式
  → 返回空字符串（不走工作流）
  → analytical 意图检测匹配
  → cognition层：intent=="analytical" and not tool_result
  → 阴方思考（DeepSeek）+ 阳方思考（Qwen）+ 太极合一
```

### 6.3 修复代码（perception.py）
```python
# ②.5 分析型问题短路：不走工作流，交给阴阳对子思考处理
# 必须在LLM语义推理之前，否则LLM会把分析型问题判定为research_report
if re.search(
    r"分析.*假设|潜在.*假设|批判|反思|反驳|论证|"
    r"逻辑.*漏洞|推理|辩证|第一性原理|苏格拉底|"
    r"反对.*理由|支持.*理由|利弊分析|优缺点分析|对比.*分析|"
    r"分析.*(?:可能性|可行性|影响|原因|趋势|前景|利弊|优缺点|风险|机会|本质|原理|影响)",
    text, re.I
):
    logger.info(f"分析型问题短路(不走工作流): text={text[:40]}")
    return ""
```

## 七、D层完整性校验
- **问题**：修改contracts.py后哈希不匹配
- **修复**：更新`d_layer/MANIFEST.json`的`expected_hashes.contracts.py`

## 八、验证结果
- 145个Python文件语法检查通过
- 服务启动正常（D层校验✓、账本✓、9模块注册✓）
- 20个并发health请求平均7.9ms
- multiagent长任务期间health请求平均2.5ms（事件循环未阻塞）
- 对子思考成功触发（阴✓阳✓，DeepSeek+Qwen双模型）
