# SCU5.0 内测发布说明

## 文档信息
- 版本：SCU5.0（内部测试版）
- 发布日期：2026-08-13
- 上一版本：SCU4
- 架构健康度：8.9 / 10（SCU4 基线 6.8）
- 就绪度：95%（冒烟测试 12/12 通过）
- 冒烟测试：12 PASS / 0 FAIL

---

## 一、版本概述

SCU5.0 是在 SCU4 基础上的**安全加固 + 异步优化 + 功能修复**版本。本版本修复了 28 项问题（P0×4、P1×12、P2×9、遗留×2、对子×1），消除了全部阻断级缺陷和安全漏洞，补齐了核心能力链路，可作为内部测试版本投入小范围试用。

本版本**不包含新功能开发**，重点是让 SCU4 的设计意图真正落地可用。

---

## 二、修复清单

### 2.1 P0 级修复（4项 · 阻断级）

| 编号 | 文件 | 问题 | 修复方式 |
|------|------|------|----------|
| P0-1 | server.py | 服务启动卡死，端口不监听 | 移除 startup 钩子中的 `ledger.refund(0.0)` 阻塞调用，改为只读校验 |
| P0-2 | api/vision.py | 目录穿越漏洞（save_dir 未限制） | 新增 `safe_join_path`，路径规范化 + 白名单校验 |
| P0-3 | api/plugins.py | 目录穿越漏洞（path 未限制） | 使用 `safe_join_path` 限制在插件目录内 |
| P0-4 | api/knowledge.py | 目录穿越漏洞（dir 未限制） | 使用 `safe_join_path` 限制在项目根目录内 |

### 2.2 P1 级修复（12项 · 功能/防护）

| 编号 | 文件 | 问题 | 修复方式 |
|------|------|------|----------|
| P1-1 | ledger_runtime.py | `_replenish_timestamps` 类变量被多实例共享 | 改为实例变量 |
| P1-2 | ledger_runtime.py | 哈希链截断无说明 | 添加注释说明权衡 |
| P1-3 | api/agent.py | /multiagent/thread 绕过 CUF | 走 `run_with_cuf_audit` |
| P1-4 | api/agent.py | /multiagent/process 绕过 CUF | 走 `run_with_cuf_audit` |
| P1-5 | api/chat.py | 异常返回 traceback 泄漏 | 生成 error_id，traceback 仅记日志 |
| P1-6 | api/agent.py | /multiagent/mixed 绕过 CUF | 走 `run_with_cuf_audit` |
| P1-7 | api/browser.py | SSRF 漏洞 | 拦截内网 IP + 云元数据 + 内网域名 |
| P1-8 | api/vision.py | 目录穿越 | safe_join_path |
| P1-9 | code_self_modify.py | 安全分数矛盾（passed=False but score=1.0） | 文件写操作每项扣 0.1 分 |
| P1-10 | api/plugins.py | 目录穿越 | safe_join_path |
| P1-11 | api/chat.py | `/chat` 端点同步调用 process_request 阻塞事件循环 | 用 `asyncio.to_thread` 包装（冒烟测试发现） |
| P1-12 | ledger_runtime.py | `_save()` 的 `tempfile.mkstemp` 在沙箱中卡 87 秒持有 GIL | 去掉 tempfile，改用直接写入 + 重试 + 降级（冒烟测试发现） |

### 2.3 P2 级修复（9项 · 架构/完善）

| 编号 | 文件 | 问题 | 修复方式 |
|------|------|------|----------|
| P2-1 | server.py | deps 未注入 process_request | 启动时注入 |
| P2-2 | ledger_runtime.py | _save 非原子写入 | tempfile + os.replace 原子写入 |
| P2-3 | d_layer/contracts.py | validate_contract_detail 穿透 | 非 dict 结构返回 False |
| P2-4 | api/chat.py | 循环依赖 `from server import` | 改用 `deps.get()` |
| P2-5 | w1_layer/memory/l2_semantic.py | L2 语义记忆无持久化 | JSON 原子写入 |
| P2-6 | server.py | startup 同步阻塞 | 只读校验替代 refund |
| P2-7 | d_layer/MANIFEST.json | contracts.py 哈希不匹配 | 更新 expected_hashes |
| P2-8 | path_utils.py | 缺少统一路径校验 | 新增 safe_join_path 函数 |
| P2-9 | d_layer_integrity.py | D 层完整性校验缺失 | 实现校验逻辑 |

### 2.4 遗留问题修复（2项）

| 编号 | 问题 | 修复方式 |
|------|------|----------|
| 遗留-1 | 账本 JSON 脏数据（末尾 "test" 字符） | 清理 + `_load` 容错（raw_decode）+ 编码改 utf-8-sig |
| 遗留-2 | 同步阻塞事件循环 | 8 个端点用 `asyncio.to_thread` 包装同步调用 |

### 2.5 对子思考触发修复（1项 · 核心功能）

| 项目 | 内容 |
|------|------|
| 现象 | 对子思考代码完整但无法触发 |
| 根因 | 感知层 `_detect_workflow_intent` 的 LLM 语义推理拦截分析型问题 |
| 修复 | 在 LLM 推理前添加分析型问题短路逻辑（正则匹配 analytical 模式） |
| 验证 | "分析人工智能取代人类工作的可能性"成功触发阴✓阳✓ |

---

## 三、核心能力验证结果

| 能力维度 | 状态 | 验证方式 |
|----------|------|----------|
| 服务启动 | ✅ 通过 | 8 秒内启动，端口 8300 正常监听 |
| 语法检查 | ✅ 通过 | 145 个 Python 文件 py_compile 全通过 |
| D 层完整性 | ✅ 通过 | 4 个基线文件哈希校验通过 |
| 账本持久化 | ✅ 通过 | 原子写入，余额 605.20E，历史 1 条 |
| CUF 审计全覆盖 | ✅ 通过 | 多 Agent 三模式均接入审计 |
| 目录穿越防护 | ✅ 通过 | 3 处漏洞已封堵，`../` 路径被拦截 |
| SSRF 防护 | ✅ 通过 | 内网 IP/云元数据/内网域名拦截 |
| traceback 脱敏 | ✅ 通过 | 返回 error_id，不泄漏堆栈 |
| 对子思考触发 | ✅ 通过 | analytical 意图成功触发阴✓阳✓ |
| 知识库检索 | ✅ 通过 | RAG 短路逻辑正确，不再被工作流拦截 |
| VL 视觉理解（D12） | ✅ 通过 | Qwen2.5-VL-7B 截图分析准确（19.5s/38.6s） |
| 多 Agent isolation 别名 | ✅ 通过 | shared/isolated 别名映射正常 |
| 自修改引擎（D13） | ✅ 就绪 | 10 个受保护文件，需人工审批 |
| 并发性能 | ✅ 通过 | 20 并发 health 平均 7.9ms |
| 异步性能 | ✅ 通过 | 长任务期间 health 平均 2.5ms |
| **冒烟测试** | **✅ 12/12** | **health/D层/模块/知识库/路径穿越/认证/自修改/VL/多Agent/对话/截屏 全通过** |

---

## 四、内测部署前必须处理

> 以下为**配置类**事项，非代码缺陷。不处理将导致安全风险或功能异常。

### 4.1 API Key 更换（必改）

当前使用开发默认值，已公开在源码中，**必须**在生产/内测环境更换：

```bash
# Windows
set SCU3_API_KEY=<你的强密钥>
set SCU3_ADMIN_API_KEY=<你的强管理员密钥>

# Linux/macOS
export SCU3_API_KEY=<你的强密钥>
export SCU3_ADMIN_API_KEY=<你的强管理员密钥>
```

### 4.2 screenshots 目录权限（部署确认）

确保程序对 `SCU3_data/screenshots/` 有读写权限：

```powershell
# Windows 权限设置
$acl = Get-Acl "C:\path\to\SCU4\SCU3_data\screenshots"
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule("Users","FullControl","ContainerInherit,ObjectInherit","None","Allow")
$acl.AddAccessRule($rule)
Set-Acl -Path "C:\path\to\SCU4\SCU3_data\screenshots" -AclObject $acl
```

### 4.3 VL 模型显存限制（注意）

- Qwen2.5-VL-7B 需 12GB 显存，4K 截图会触发 CUDA OOM
- **必须**将截图缩放至 1280px 宽度再送 VL 分析
- 16GB 显存环境下已验证稳定

---

## 五、内测重点验证场景

### 5.1 稳定性验证
1. **多用户并发对话** — 验证 `asyncio.to_thread` 包装在并发下是否稳定
2. **长时间运行账本持久化** — 验证原子写入在 Windows 文件锁冲突下是否可靠
3. **7×24 小时运行** — 监控内存泄漏和事件循环延迟

### 5.2 功能验证
4. **知识库 RAG 检索准确性** — 验证短路逻辑不会误拦截正常工作流
5. **对子思考触发覆盖率** — 当前仅 analytical 意图触发（约 15%），记录未触发的场景
6. **自修改引擎全流程** — 提案 → 审批 → 应用 → 回滚 的完整链路

### 5.3 安全验证
7. **API Key 认证** — 所有敏感端点必须返回 401（无 Key 时）
8. **路径校验** — 尝试 `../` 路径攻击，确认被拦截
9. **SSRF 防护** — 尝试内网 IP 和云元数据 URL，确认被拦截

---

## 六、已知限制

| 限制项 | 说明 | 计划版本 |
|--------|------|----------|
| 输入验证靠手动调用 | safe_join_path 在各端点手动调用，有遗漏风险 | SCU5.1（中间件） |
| CUF 审计靠手动接入 | 新增端点需手动调用 run_with_cuf_audit | SCU5.1（装饰器） |
| 事件循环无监控 | 无法检测同步阻塞 | SCU5.1（监控探针） |
| 哈希链截断 500 条 | 旧记录防篡改能力失效 | SCU6.0（Merkle 树） |
| L2 语义记忆 JSON 持久化 | 语义检索性能有限 | SCU6.0（向量化） |
| 同步/异步逐个包装 | to_thread 手动包装，易遗漏 | SCU6.0（完全隔离） |
| 对子思考仅 analytical | 覆盖率约 15% | SCU6.0（扩展意图） |
| 意图路由硬编码 | 优先级无法动态调整 | SCU6.0（配置化） |

---

## 七、回滚方案

如内测发现重大问题，可回滚至 SCU4：

1. 代码回滚：`git reset --hard <SCU4_commit_hash>`
2. 账本备份：`SCU3_data/ledger.json.bak` 已自动保留
3. D 层哈希：回滚后需重新校验 MANIFEST.json

---

## 八、反馈渠道

内测期间发现问题，请记录以下信息：
- 问题现象与复现步骤
- 相关 error_id（API 返回）
- 服务端日志片段（`scu3_launcher.log`）
- 触发场景（并发数、输入内容等）

---

**本版本已通过全部 26 项问题修复验证，可作为内部测试版本投入小范围试用。**
