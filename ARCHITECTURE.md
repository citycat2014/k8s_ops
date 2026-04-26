# K8s 运维诊断智能体 — 架构设计文档

> 版本: v0.1 | 日期: 2026-04-26 | 状态: 已实现

---

## 一、技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | Agent 生态最成熟 |
| LLM API | 原生 OpenAI API | 直接使用 OpenAI SDK，无需额外框架依赖，代码更简洁可控 |
| K8s 交互 | **kubectl CLI**（subprocess） | 运维人员最熟悉，排查过程可直接复现，无额外 SDK 依赖 |
| CLI | Typer | 简洁、类型校验 |
| 配置 | Pydantic + YAML | 配置校验、类型安全 |
| 知识库 | TF-IDF (纯 Python) | 无向量数据库依赖，轻量级检索 |

---

## 二、架构设计

### 2.1 总体架构

```
┌─────────────────────────────────────────────────┐
│                   CLI (Typer)                    │
│  k8s-diagnose "排查 order-service Pod 失败"      │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│              DiagnoseAgent (LLM Agent)            │
│                                                   │
│  ┌──────────────┐    ┌──────────────────────┐    │
│  │ ReAct Loop   │───▶│ ThoughtChain         │    │
│  │ (原生实现)    │    │ 观察→假设→验证→结论   │    │
│  └──────────────┘    └──────────────────────┘    │
│       │                                         │
│       ▼                                         │
│  ┌──────────────────────────┐                    │
│  │ Tools (kubectl 封装)     │                    │
│  │ get_pod, get_logs, ...   │                    │
│  └───────────┬──────────────┘                    │
└──────────────┼───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│         KubectlRunner (权限校验层)                │
│  1. 检查子命令白名单                              │
│  2. 检查关键字黑名单                              │
│  3. subprocess.run(["kubectl", ...])              │
│  4. 记录审计日志                                  │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│              kubectl (本地 CLI)                   │
└──────────────────────────────────────────────────┘
```

### 2.2 数据流

```
用户查询
  → Agent 解析目标资源（namespace/pod-name）
  → Agent 调工具: kubectl_get_pod → KubectlRunner 执行 kubectl get pod -o yaml
  → 返回结果记录到 ThoughtChain (observation)
  → Agent 分析结果，形成假设 (hypothesis)
  → Agent 调下一个工具: kubectl_describe_pod → 获取 events
  → 返回结果记录到 ThoughtChain (verification)
  → ... 循环直到收敛
  → 输出结构化报告
```

### 2.3 知识库检索

```
用户查询
  → KnowledgeRetriever 检索相关知识
    → 扫描 knowledge/ 目录下的 .md 文件
    → TF-IDF 计算相关性
    → 返回 top-k 相关文档
  → 相关知识注入 LLM 上下文
  → Agent 结合知识进行诊断
```

---

## 三、关键组件设计

### 3.1 KubectlRunner — 命令执行器

**职责**：封装 kubectl subprocess 调用，统一权限校验。

**权限模式**：

| 模式 | 允许的子命令 |
|------|-------------|
| read-only（默认） | get, describe, top, cluster-info, version, auth, api-resources, api-versions, explain |
| diagnostic | + logs, exec, cp |
| read-write | + delete, patch, scale, cordon, uncordon, drain, label, annotate, taint, apply, create |

**安全检查流程**：
1. 检查子命令是否在白名单内
2. 检查命令参数是否匹配 shell 元字符（`|`, `;`, `$`, `` ` ``）
3. 检查命令参数是否匹配关键字黑名单
4. 检查是否包含敏感参数（--kubeconfig, --server, --token 等）
5. 执行 subprocess，设置 30s timeout
6. 记录命令到审计日志

**输入/输出**：
```
输入: runner.run("get", "pod", "my-pod", "-n", "default", "-o", "yaml")
输出: KubectlResult(stdout, stderr, returncode, command)
```

**CNI 自动检测**：
- `discover_cni_plugin()` 自动检测集群使用的 CNI（calico/cilium/flannel/weave）
- `find_namespace_by_pod(pattern)` 根据 pod 名模糊查找 namespace

### 3.2 Tools — kubectl 工具集

每个工具函数封装一条 kubectl 命令，LLM 通过 tool calling 调用。共 **29 个工具**：

**通用工具（17 个）**：

| 工具 | 对应命令 | 用途 |
|------|---------|------|
| `kubectl_get_pod` | `get pod <name> -o yaml` | 完整配置+状态 |
| `kubectl_describe_pod` | `describe pod <name>` | 人可读详情+events |
| `kubectl_get_logs` | `logs <name> --tail 200` | 容器日志 |
| `kubectl_get_events` | `get events --sort-by` | 事件列表 |
| `kubectl_list_pods` | `get pods -o wide` | 列出所有 Pod |
| `kubectl_describe_node` | `describe node` | 节点详情 |
| `kubectl_get_deployment` | `get deployment` | Deployment 状态 |
| `kubectl_get_replicaset` | `get replicaset` | ReplicaSet 详情 |
| `kubectl_get_resource_quotas` | `get resourcequotas` | 资源配额 |
| `kubectl_get_pvc` | `get pvc` | PVC 状态 |
| `kubectl_get_endpoints` | `get endpoints` | Service 后端 |
| `kubectl_get_configmap` | `get configmap` | ConfigMap |
| `kubectl_get_ingress` | `get ingress` | Ingress |
| `kubectl_get_daemonset` | `get daemonset` | DaemonSet |
| `kubectl_get_statefulset` | `get statefulset` | StatefulSet |
| `kubectl_get_service` | `get service` | Service |
| `kubectl_get_nodes` | `get nodes -o wide` | 节点列表 |
| `kubectl_find_namespace` | `get pods -A` → 匹配 pattern | 根据 pod 名查找 namespace |

**CNI 专用工具（6 个）**：

| 工具 | 对应命令 | 用途 |
|------|---------|------|
| `kubectl_get_cni_pods` | `get pods -n kube-system -l k8s-app=calico-node/cilium/flannel` | 查看 CNI 插件状态 |
| `kubectl_get_cni_configmap` | `get configmap -n kube-system <cni-config>` | 查看 CNI 网络配置 |
| `kubectl_get_cni_logs` | `logs -n kube-system <cni-pod> --tail 100` | 查看 CNI 插件日志 |
| `kubectl_get_networkpolicy` | `get networkpolicy -n <ns>` | 查看网络策略规则 |
| `kubectl_get_endpoint_slices` | `get endpointslices -n <ns>` | 查看 endpoint 端点 |
| `kubectl_describe_pod_network` | `describe pod <name>` 解析 network events | 检查 Pod 网络创建事件 |

**Volcano 专用工具（6 个）**：

| 工具 | 对应命令 | 用途 |
|------|---------|------|
| `kubectl_get_podgroup` | `get podgroup -n <ns>` | 查看 PodGroup CRD 状态 |
| `kubectl_get_queue` | `get queue` | 查看 Volcano 队列 |
| `kubectl_get_vcjob` | `get vcjob -n <ns>` | 查看 Volcano Job 状态 |
| `kubectl_describe_podgroup` | `describe podgroup <name> -n <ns>` | 查看 PodGroup 详情+events |
| `kubectl_get_volcano_scheduler_config` | `get configmap -n volcano-system volcano-scheduler-configmap` | 查看调度器配置 |
| `kubectl_get_volcano_scheduler_logs` | `logs -n volcano-system deploy/volcano-scheduler --tail 100` | 查看调度器日志 |

**返回值**：kubectl 原始输出文本，格式化为 LLM 友好的结构。

### 3.3 ThoughtChain — 思维链

**职责**：记录诊断过程中 LLM 的每一步推理。

**节点类型**：

| 类型 | 含义 | 示例 |
|------|------|------|
| observation | 观察到了什么 | Pod Phase=Pending, 无 IP |
| hypothesis | 可能是什么原因 | 调度失败（资源不足/Taint/亲和性） |
| verification | 验证动作+结果 | events 显示 Insufficient memory |
| conclusion | 确认根因 | 集群内存不足，无法满足 2Gi request |
| action | 执行的工具调用 | kubectl describe pod xxx |

**上下文压缩**：支持 `context_compression` 模式，将思维链压缩为紧凑符号格式，减少 token 使用量约 40-50%。

**展示方式**（用户视角）：
```
👁 [observation] Pod order-service Phase=Pending, 无 IP 分配
💡 [hypothesis] 可能是调度失败
⚡ [action] kubectl describe pod order-service -n default
👁 [observation] Events: "0/3 nodes available: Insufficient memory"
🔍 [verification] kubectl describe node → 确认内存耗尽
✅ [conclusion] 集群内存资源不足
```

### 3.4 DiagnoseAgent — 主循环

基于 **原生 OpenAI API 实现的 ReAct 模式**：
1. LLM 收到用户查询 + 已收集的思维链上下文 + 相关知识
2. LLM 决定调用哪个工具（function calling）
3. KubectlRunner 执行，返回结果
4. 结果注入 ThoughtChain + 下一轮 LLM 输入
5. 循环直到 LLM 输出最终诊断或达到最大迭代次数

**拦截机制**：
- 拦截 LLM 的 tool calls → 记录到 ThoughtChain (action)
- 拦截工具返回结果 → 提取关键信息记录到 ThoughtChain (observation)

### 3.5 KnowledgeRetriever — 知识库检索

**职责**：基于 TF-IDF 的轻量级知识检索，无需外部向量数据库。

**工作流程**：
1. 加载 `knowledge/` 目录下的所有 `.md` 文件
2. 解析 YAML frontmatter 提取元数据
3. 分词并构建 TF-IDF 索引
4. 根据查询返回 top-k 相关文档
5. 将相关知识注入 LLM 上下文

**知识库目录结构**：
```
knowledge/
├── error-patterns/     # 错误模式文档
│   ├── crashloopbackoff.md
│   ├── imagepullbackoff.md
│   └── faileddcheduling.md
├── runbooks/          # 运维手册
│   └── pod-diagnosis.md
└── command-guides/    # 命令指南
    └── kubectl-basics.md
```

### 3.6 Error Patterns — 错误模式库

预定义 **8 种**常见 K8s 错误模式：

| 错误码 | 模式名称 | 触发条件 |
|--------|---------|---------|
| E001 | ImagePullBackOff | Container 状态 Waiting + ImagePullBackOff |
| E002 | CrashLoopBackOff | Container 状态 Waiting + CrashLoopBackOff |
| E003 | OOMKilled | Container 状态 Terminated + OOMKilled |
| E004 | FailedScheduling | Pod 长时间 Pending + FailedScheduling 事件 |
| E005 | Unhealthy | Running + Liveness/Readiness probe 失败 |
| E006 | CNI 插件异常 | CNI DaemonSet Pod 非 Running / Pod 网络创建失败 |
| E007 | Pod 网络不通 | Pod Running 但跨 Pod/Service 通信失败 |
| E008 | Volcano Gang Scheduling 死锁 | PodGroup Pending + 部分 Pod 运行 + 剩余无法调度 |

### 3.7 Analyzers — 分析器

目前已实现的分析器：

| 分析器 | 文件 | 用途 |
|--------|------|------|
| PodAnalyzer | `analyzers/pod_analyzer.py` | 解析 Pod YAML，匹配容器状态到错误模式 |
| SchedulerAnalyzer | `analyzers/scheduler.py` | 分析 FailedScheduling 事件 |

**注**：CNI 分析器和 Volcano 分析器暂未实现，相关诊断通过 Agent 直接调用专用工具完成。

---

## 四、CLI 使用方式

```bash
# 单次诊断
k8s-diagnose "排查 default 下 order-service Pod 启动失败"

# 指定 namespace
k8s-diagnose -n kube-system "排查 coredns 启动失败"

# 交互模式
k8s-diagnose -i

# 显示思维链（默认开启）
k8s-diagnose --show-thoughts "排查 xxx"
k8s-diagnose --no-thoughts "排查 xxx"  # 关闭

# 放宽权限
k8s-diagnose --mode diagnostic "排查 xxx"

# 使用配置文件
k8s-diagnose --config config.yaml "排查 xxx"
```

### 配置文件示例

```yaml
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.1
  api_key: ""           # 或从环境变量 OPENAI_API_KEY 读取
  base_url: ""          # 自定义 API 地址

k8s:
  kubeconfig: null      # 默认使用 ~/.kube/config
  default_namespace: default
  mode: read-only       # read-only | diagnostic | read-write
  bypass_blacklist: false

agent:
  max_tool_calls: 20
  timeout_seconds: 120
  show_thoughts: true
  context_compression: true

knowledge:
  enabled: true
  knowledge_dir: knowledge
  max_results: 3
  min_score: 0.01
  max_injected_chars: 4000
```

---

## 五、项目结构

```
k8s_ops/
├── pyproject.toml
├── REQUIREMENTS.md             # 产品需求文档
├── ARCHITECTURE.md             # 架构设计文档（本文档）
├── README.md                   # 快速开始指南
├── knowledge/                  # 知识库目录
│   ├── error-patterns/         # 错误模式文档
│   ├── runbooks/              # 运维手册
│   └── command-guides/        # 命令指南
├── k8s_diagnose/
│   ├── __init__.py
│   ├── __main__.py             # 入口
│   ├── cli.py                  # Typer CLI
│   ├── config.py               # Pydantic 配置
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── tools.py            # 29 个 kubectl 工具
│   │   ├── prompts.py          # System prompt
│   │   ├── orchestrator.py     # DiagnoseAgent (ReAct + 思维链)
│   │   ├── state.py            # 诊断状态
│   │   └── thought_chain.py    # ThoughtChain 模型
│   ├── k8s_client/
│   │   ├── __init__.py
│   │   ├── kubectl.py          # KubectlRunner
│   │   └── permissions.py      # 命令白名单 + 关键字黑名单
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── base.py             # 分析器基类
│   │   ├── pod_analyzer.py     # Pod 状态诊断
│   │   └── scheduler.py        # 调度失败分析
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── error_patterns.py   # 8 种错误模式定义
│   │   └── retriever.py        # TF-IDF 知识检索
│   └── utils/
│       ├── __init__.py
│       └── format.py           # 结构化输出格式化
└── tests/
    ├── __init__.py
    ├── conftest.py             # pytest fixtures
    ├── test_k8s_client/        # kubectl 执行 + 权限测试
    ├── test_analyzers/         # 分析器测试
    ├── test_agent/             # Agent 测试
    └── test_knowledge/         # 知识库测试
```

---

## 六、实现阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1** 基础设施 | pyproject.toml + config.py + KubectlRunner + 白名单 + 黑名单 + 测试 | ✅ 已完成 |
| **Phase 2** Agent 核心 | 29 个工具 + 原生 ReAct + ThoughtChain + 测试 | ✅ 已完成 |
| **Phase 3** 知识库 | 8 种错误模式库 + TF-IDF 检索器 + Pod/Scheduler 分析器 + 测试 | ✅ 已完成 |
| **Phase 4** CLI 集成 | Typer CLI + __main__.py + README + e2e 测试 | ✅ 已完成 |

---

## 七、依赖清单

```toml
[project]
name = "k8s-diagnose"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0.0",
    "typer>=0.9.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov",
    "ruff>=0.3.0",
    "pyright>=1.1",
]

[project.scripts]
k8s-diagnose = "k8s_diagnose.__main__:main"
```

> 注意：**不需要 `kubernetes` Python SDK**，只用 `kubectl` CLI（subprocess 调用）。

---

## 八、测试策略

**不依赖真实集群**：

1. **KubectlRunner 层**：mock `subprocess.run`
   - 模拟各种 kubectl 输出（Pod yaml、events、logs）
   - 验证权限校验：白名单拒绝非白名单命令
   - 验证黑名单：拦截包含危险参数的命令

2. **工具层**：mock KubectlRunner
   - 验证工具返回值格式和错误处理

3. **分析器层**：直接构造 kubectl 输出的 YAML 字符串
   - PodAnalyzer.parse_pod_yaml(yaml_str) → 验证诊断

4. **Agent 层**：mock kubectl 返回值 + mock LLM
   - 验证思维链记录正确性
   - 验证端到端诊断收敛性

---

## 九、安全设计总结

```
┌──────────────────────────────────────────┐
│  安全检查层级（由外到内）                  │
│                                          │
│  1. 子命令白名单（permissions.py）         │
│     → 非白名单子命令直接拒绝               │
│                                          │
│  2. Shell 元字符检查（kubectl.py）         │
│     → | ; $ ` 等注入字符拒绝               │
│                                          │
│  3. 敏感参数检查（kubectl.py）             │
│     → --kubeconfig, --server 等参数拒绝   │
│                                          │
│  4. 关键字黑名单（permissions.py）         │
│     → delete/patch/scale 等参数拒绝       │
│                                          │
│  5. subprocess timeout（kubectl.py）       │
│     → 超时 30s 自动终止                    │
│                                          │
│  6. Agent 层 max_tool_calls               │
│     → 最多 20 次工具调用                   │
└──────────────────────────────────────────┘
```
