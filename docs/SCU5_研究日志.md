# SCU5.0 研究日志

## 文档信息
- 项目：SCU（标准计算单元）
- 时间跨度：2026-08-11 至 2026-08-12
- 记录人：ruoshui-xiaoxiang

## 第一部分：2026-08-11（SCU2→SCU3.0 开源）

### 1.1 浏览器能力扩展（01:15-01:39）
- 用户询问SCU2能否像Trae Agent一样打开浏览器查看屏幕
- 评估SCU2现有能力：web_search工具（DuckDuckGo HTML解析）但缺少浏览器自动化、屏幕截取、GUI控制
- 集成Qwen2.5-VL-7B（双模型切换方案A）：修改local_model.py添加model_type（text/vl），实现chat_with_image和switch_model_type
- 新增端点：/local-model/switch-type、/vision/chat、/vision/status

### 1.2 自动化能力建设（01:39-02:09）
- 完成Playwright浏览器自动化、httpx+BeautifulSoup网页抓取、mss屏幕截取、pyautogui桌面控制
- 新增w1_layer/automation.py，server.py添加21个端点（/browser/*、/web/*、/screen/*、/desktop/*、/vision/analyze-screen）
- 修复网络超时：默认超时30s，3次重试+指数退避，测试改用本地HTTP服务器

### 1.3 EXE启动器与多Agent（02:43-03:06）
- 创建SCU2启动器.exe（6.49MB）：自动检测Python、端口检查、自动开浏览器、实时日志
- 部署方案注入知识库（doc_id=41）
- 实现三种多Agent模式：thread（共享上下文）、process（隔离上下文，~100ms开销）、mixed（按任务指定隔离级别）
- 新增端点：POST /multiagent/thread、/multiagent/process、/multiagent/mixed、GET /multiagent/modes

### 1.4 架构合规性验证（03:06-03:45）
- 验证5项架构原则、5个守卫点、三维度分离、业务合并、D层只读——全部符合
- 识别4个关键问题（插件钩子未触发、卸载端点未返回503、禁用持久化恢复破损、knowledge.base loader引用错误）+3个中等问题
- 修复7项问题，模块化评分从62/100提升到~90/100

### 1.5 八类检查与技术分析（03:45-04:32）
- 完成8类检查（架构、模块化、全功能、数据流、全测试、饱和攻击、代码逻辑、软实现）
- 生成完整技术分析文件和多维度横向测评报告，注入知识库（doc_id=78,79）
- 解决HuggingFace模型拉取超时：设置HF_HUB_OFFLINE=1和TRANSFORMERS_OFFLINE=1

### 1.6 对话功能修复（04:32-09:28）
- 修复API Key未附加到/chat/stream请求导致401错误
- 模型下拉框更新为显示6个支持平台（DeepSeek、通义千问/Kimi/智谱GLM云模型，LM Studio/Ollama本地模型）
- 调整llm_client.py读取DASHSCOPE_API_KEY环境变量
- 修复RAG上下文将技术文档注入闲聊：过滤greeting/conversation意图的RAG
- 修复上下文连接：memory.store()从未调用、llm_client.chat()缺少history参数、/chat/stream跳过记忆层

### 1.7 前端测试与后端验证（09:13-09:47）
- 前端测试覆盖10个功能，添加favicon.ico端点、20个缺失端点、3个路径别名、3个f-string修复、2个死代码清理
- 后端8类检查全部通过，3个低风险问题符合≤3标准
- 上下文连接验证："我叫测试用户"→"我叫什么名字"正确回答

### 1.8 自主能力闭环（09:47-10:24）
- 实现experience_store.py模块：经验存储（积累、预加载、衰减、强化）
- 修改cognition.py在插件成功后沉淀经验
- 修改action.py处理时检查经验进行预加载
- 修改perception.py添加6种新意图识别
- 验证：经验积累→强化→匹配→预加载→意图识别全闭环

### 1.9 自演化验证（10:24-11:46）
- 修复LLM输出JSON截断导致_parse_llm_output失败
- pdf_read工具3次失败触发自演化扫描（fail_count阈值）
- LLM生成提案提交CodeSelfModifier，被AST安全审查拒绝（缩进语法错误）——证明安全防护有效
- 修复浏览器同步/异步冲突：asyncio.to_thread包装sync_playwright
- 修复SBERT CUDA崩溃：CUDA→CPU fallback

### 1.10 百度搜索优化（15:03-16:14）
- 修复百度重定向链接：从搜索结果块的mu属性提取真实URL
- 强制全流程改造：action.py优先百度，knowledge_query/conversation/greeting/web_search主动注入web_search
- cognition.py改OR为AND逻辑：search_context + deep_crawl + rag_context综合注入

### 1.11 官方API集成（17:06-17:20）
- 集成百度百科、Wikipedia API
- 集成10个非爬取官方API（GitHub、Arxiv、Hacker News等）
- GitHub集成安全优化：配置GITHUB_TOKEN、域名白名单验证

### 1.12 150题测试100%通过（19:05-19:12）
- 添加followup和analytical意图检测
- 增强上下文历史注入
- 跳过followup/analytical意图的强制搜索
- 150题测试100%通过率，生成最终测试分析报告

### 1.13 SCU3.0开源（20:08-23:56）
- 生成SCU3.0架构PPT（13页16:9）
- 分析SCU区块链架构 vs 传统区块链
- 选择MIT许可证
- 创建GitHub仓库：https://github.com/ruoshui-xiaoxiang/SCU3
- 上传完整源码，发布Release v3.0.0

## 第二部分：2026-08-12（SCU3→SCU4→SCU5.0 安全加固）

### 2.1 项目整理（08:36-09:03）
- 归档散落SCU/CUF文件到E:\SCU_CUF_归档
- 创建E:\SCU3_完整版存档，重命名13个SCU2文件为SCU3
- 修复esc()函数转义HTML标签导致太极图标不显示
- UI布局调整：对子模式框和API标签移至顶栏

### 2.2 桌面版开发（10:06-10:35）
- 基于浏览器UI蓝图开发桌面版
- 解决黑框问题：VBScript启动器、PowerShell脚本、subprocess、Windows API隐藏控制台
- 修复中文名bat文件GBK编码错误

### 2.3 插件市场修复（12:05-12:24）
- PDF读取：移除无效_safe_path导入
- 翻译：切换到MyMemory，添加语言代码映射
- 二维码：调整正则优先级（二维码检测优先于GitHub搜索）

### 2.4 Agent面板任务编排（12:24-12:43）
- 添加目标输入区、执行模式选择、计划/执行按钮、模板快捷区、实时操作面板
- 提交commit 662b4ac（104文件变更）

### 2.5 CUF审计集成（12:43-13:24）
- 发现工作流执行路径绕过CUFLogicFirewall
- 创建guard/workflow_guard.py封装三阶段审批链（W2→M守卫、工具守卫、M→W2守卫）
- 集成到/agent/run、/multiagent/execute等端点

### 2.6 工作流自动触发（13:18-13:53）
- 添加工作流自动路由到对话框
- 实现三层触发架构：强信号词、宽松动词、LLM语义推理
- 上下文感知：传入历史区分追问vs新话题
- 提交commit e01972e

### 2.7 代码审查与修复（14:32-15:58）
- 6个关键问题：/agent/plan缺CUF审批循环、前端调用不存在端点、熵税余额耗尽、_safe_path重复代码、异常吞噬、MCP缺失DELETE方法
- 修复全部9类问题，创建core/abc.py抽象基类
- m_layer拆分为4个子包：orchestration/、plugins/、_multimodal/、evolution/
- server.py从3624行拆分到1225行，创建24个域路由文件，迁移230条路由

### 2.8 SCU4打包（16:03-16:58）
- 清理m_layer子包占位文件，迁移15+6+3+8个文件
- 32个模块通过sys.modules别名注册，确保旧导入路径零变化
- SCU4打包到桌面，推送到仓库commit 29104a6
- 发现并修复local_model.py的MODELS_DIR路径错误（dirname层数不足）

### 2.9 SCU4全面检测与P0/P1/P2修复（17:45-18:39）
- 更新前端版本号为SCU4 v6.0
- 全面代码检验发现启动卡点、3个目录穿越漏洞
- P0修复：移除ledger.refund阻塞调用、新增safe_join_path
- P1修复：账本并发安全、API响应泄漏traceback、多Agent绕过CUF、SSRF防护、安全分数矛盾、契约校验穿透
- P2修复：L2语义记忆持久化、哈希链截断说明、循环依赖
- 遗留问题修复：账本JSON脏数据、同步阻塞事件循环（asyncio.to_thread）

### 2.10 对子思考触发修复（18:57）
- **核心发现**：对子思考代码完整实现但无法触发
- **根因**：感知层_detect_workflow_intent的LLM语义推理拦截分析型问题
- **修复**：在LLM推理前添加分析型问题短路逻辑
- **验证**："分析人工智能取代人类工作的可能性"成功触发阴✓阳✓

## 第三部分：关键技术决策记录

### 3.1 架构演进路径
SCU2（单模型） → SCU3.0（阴阳对子+CUF守卫+开源） → SCU4（模块化重构） → SCU5.0（安全加固+异步优化）

### 3.2 核心设计原则
- 四层架构：D层（定义）→ M层（认知）→ W1层（执行）→ W2层（感知）
- 三维度分离：数据流、守卫点、依赖方向
- D层只读：运行时状态归W1层
- CUF守卫：所有跨层操作必须经过审计+熵税

### 3.3 安全加固策略
- 最小权限：API Key/Token认证
- 纵深防御：路径校验+SSRF防护+traceback脱敏
- 完整性校验：D层哈希基线
- 原子操作：临时文件+os.replace避免文件锁冲突
