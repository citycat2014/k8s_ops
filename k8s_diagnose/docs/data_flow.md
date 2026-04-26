# K8s 运维诊断智能体 — 数据流转图

## 架构总览

```
                          ┌─────────────────────────────────────────────────────┐
                          │                    CLI 层 (cli.py)                   │
                          │  typer.Argument(query) + Options(namespace/mode/..)  │
                          └─────────────────────┬───────────────────────────────┘
                                                │ query, config
                                                ▼
                 ┌──────────────────────────────────────────────────┐
                 │              Config (config.py)                   │
                 │  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐│
                 │  │ LLM     │ │ K8s      │ │ Agent   │ │Knowledge││
                 │  │ model   │ │ namespace│ │ max_tool│ │ enabled││
                 │  │ temp    │ │ mode     │ │ timeout │ │ top_k  ││
                 │  └─────────┘ └──────────┘ └─────────┘ └────────┘│
                 └─────────────────────┬────────────────────────────┘
                                       │
                                       ▼
                 ┌──────────────────────────────────────────────────┐
                 │         DiagnoseAgent (orchestrator.py)           │
                 │                                                   │
                 │  ┌───────────────────┐     ┌──────────────────┐  │
                 │  │ KnowledgeRetriever│◄────│  query           │  │
                 │  │ (retriever.py)    │     │                  │  │
                 │  │                   │     │  TF-IDF scoring  │  │
                 │  │  knowledge/*.md ──┘     │                  │  │
                 │  └────────┬──────────┘     └────────┬─────────┘  │
                 │           │ knowledge_context        │            │
                 │           ▼                          │            │
                 │  ┌───────────────────────────────────┴──────┐    │
                 │  │         ReAct Agent（原生 OpenAI API）    │    │
                 │  │                                          │    │
                 │  │  HumanMessage(knowledge + query)         │    │
                 │  │        │                                 │    │
                 │  │        ▼                                 │    │
                 │  │  ┌──────────┐   tool_calls   ┌───────┐  │    │
                 │  │  │   LLM   │─────────────────►│ Tool  │  │    │
                 │  │  │(Claude)  │◄────────────────│Result │  │    │
                 │  │  └──────────┘  observation    └───┬───┘  │    │
                 │  │        │                          │       │    │
                 │  │        │         ←── ReAct 循环 ──┘       │    │
                 │  │        │                                  │    │
                 │  │        ▼                                  │    │
                 │  │  AIMessage(final_diagnosis)               │    │
                 │  └──────────────────────┬────────────────────┘    │
                 │                         │                          │
                 └─────────────────────────┼──────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
         ┌──────────────────┐  ┌────────────────────┐  ┌─────────────────┐
         │   ThoughtChain   │  │   29 个 Tools       │  │   分析器 (未激活) │
         │ (thought_chain)  │  │      Tools          │  │                 │
         │                  │  │ (agent/tools.py)    │  │ PodAnalyzer     │
         │ observation      │  │                     │  │ SchedulerAnalyzer│
         │ action+tool_call │  │ ┌─────────────────┐ │  └─────────────────┘
         │ tool_result      │  │ │ 共享 KubectlRunner│ │
         └────────┬─────────┘  │ │  _get_runner()  │ │
                  │            │ └────────┬────────┘ │
                  │            └──────────┼──────────┘
                  │                       │
                  ▼                       ▼
         ┌─────────────────┐    ┌────────────────────────────────────┐
         │  诊断报告输出    │    │       安全校验链 (kubectl.py)       │
         │                 │    │                                     │
         │ ## 症状         │    │  1. 子命令白名单  _check_subcommand  │
         │ ## 排查思维链   │    │  2. Shell注入检测 _check_shell_inj   │
         │ ## 诊断结果     │    │  3. 敏感参数拦截  _check_sensitive   │
         │ ## 执行过命令   │    │  4. 全局黑名单    _check_blacklist   │
         └─────────────────┘    │         │                           │
                                └─────────┼───────────────────────────┘
                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │  kubectl 子进程   │
                                 │  subprocess.run   │
                                 │  (timeout=30s)    │
                                 └────────┬──────────┘
                                          │ stdout / stderr
                                          ▼
                                 ┌─────────────────┐
                                 │  Kubernetes API  │
                                 │  (via kubectl)    │
                                 └─────────────────┘
```

## CNI 自动发现子流程

```
  kubectl_get_cni_pods(plugin="")
            │
            ├─ plugin 有值 ──────► 直接用该 plugin 执行查询
            │
            └─ plugin 为空 ──────► runner.discover_cni_plugin()
                                         │
                                         ├─ kubectl get ds -n kube-system -l k8s-app=calico-node
                                         ├─ kubectl get ds -n kube-system -l k8s-app=cilium
                                         ├─ kubectl get ds -n kube-system -l k8s-app=kube-flannel-ds
                                         └─ kubectl get ds -n kube-system -l k8s-app=weave-net
                                                    │
                                        首个返回成功的即为当前 CNI
                                                    │
                                         返回 (label, configmap_name)
                                                    │
                                                    ▼
                                   用检测到的 plugin 执行实际查询
```

## 安全校验链

```
  工具调用 kubectl.run("get", "pod", "my-pod", "-n", "default")
            │
            ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Step 1: _check_subcommand(args[0])                     │
  │  检查 "get" 是否在 ALLOWED_KUBECTL_COMMANDS[mode] 中     │
  │  读-写模式分离: read-only ≠ diagnostic ≠ read-write      │
  └────────────────────────┬────────────────────────────────┘
                           │ PASS
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Step 2: _check_shell_injection(args)                   │
  │  检测 | ; $ ` $( 等 shell 元字符                          │
  └────────────────────────┬────────────────────────────────┘
                           │ PASS
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Step 3: _check_sensitive_params(args)                  │
  │  拦截 --kubeconfig / --server / --token / --as 等        │
  │  防止覆盖集群认证上下文                                    │
  └────────────────────────┬────────────────────────────────┘
                           │ PASS
                           ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Step 4: _check_blacklist(args)                         │
  │  ├─ GLOBAL_BLACKLIST: --force / --grace-period=0        │
  │  │  (任何模式都拦截)                                      │
  │  └─ RESTRICTED_KEYWORDS: delete / patch / scale 等       │
  │     (仅 READ_WRITE 模式放行)                              │
  └────────────────────────┬────────────────────────────────┘
                           │ PASS
                           ▼
                    subprocess.run(cmd)
                           │
                  kubectl → Kubernetes API
```

## ReAct 循环详情

```
  Round 1
  ┌──────────────────────────────────────────────┐
  │  LLM 输入:                                    │
  │    <knowledge> TF-IDF 检索到的排查指南 </knowledge> │
  │    问题: pod my-app 启动失败                   │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────┐
  │  LLM 决策: 先查看 Pod 详情                    │
  │  Tool: kubectl_describe_pod("my-app")         │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────┐
  │  工具返回: Phase=Pending, events=FailedScheduling │
  │  ThoughtChain 记录:                           │
  │    [观察] 用户请求: pod my-app 启动失败          │
  │    [行动] 调用工具 kubectl_describe_pod         │
  │    [观察] Pod Phase=Pending, events=Failed...  │
  └──────────────────┬───────────────────────────┘
                     │
  Round 2            │
  ┌──────────────────┼───────────────────────────┐
  │  LLM 输入:                                    │
  │    已收集信息: 上述 ThoughtChain 上下文         │
  │    LLM 决策: 检查集群事件和 node 资源           │
  │    Tool: kubectl_get_events(field_selector=FailedScheduling) │
  └──────────────────┬───────────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────────┐
  │  工具返回: Insufficient cpu on node-1, node-2   │
  │  ThoughtChain 追加记录                        │
  └──────────────────┬───────────────────────────┘
                     │
  Round N            │
  ┌──────────────────┼───────────────────────────┐
  │  LLM 信息充足，生成最终诊断报告                 │
  │  包含: 症状 / 根因 / 证据 / 建议修复            │
  └──────────────────────────────────────────────┘
```

## 关键文件映射

| 模块 | 文件 | 职责 |
|------|------|------|
| CLI 入口 | `cli.py` / `__main__.py` | Typer CLI，解析参数，启动 async 循环 |
| 配置管理 | `config.py` | Pydantic 配置类 (LLM/K8s/Agent/Knowledge) |
| Agent 编排 | `agent/orchestrator.py` | DiagnoseAgent，ReAct 循环 + 报告生成 |
| 系统提示 | `agent/prompts.py` | SYSTEM_PROMPT 模板 |
| 工具定义 | `agent/tools.py` | 29 个 @tool 函数，共享 KubectlRunner |
| 思维链 | `agent/thought_chain.py` | ThoughtNode 记录诊断过程 |
| kubectl 执行 | `k8s_client/kubectl.py` | 4 层安全检查 + subprocess + CNI 自动发现 |
| 权限策略 | `k8s_client/permissions.py` | 子命令白名单 + 全局/受限黑名单 |
| 知识库 | `knowledge/retriever.py` | TF-IDF 检索 knowledge/*.md |
| 错误模式 | `knowledge/error_patterns.py` | 8 种已知错误模式 (E001-E008) |
| 分析器 | `analyzers/pod_analyzer.py` / `scheduler.py` | 独立分析组件（当前未接入 ReAct 循环） |
