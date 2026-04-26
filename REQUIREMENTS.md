# K8s 运维诊断智能体 — 产品需求文档

> 版本: v0.1 | 日期: 2026-04-26 | 状态: 已实现

---

## 一、背景与目标

### 1.1 问题

K8s 运维人员排查 Pod 异常需要手动执行一系列 kubectl 命令：

```bash
kubectl describe pod order-service -n default   # 看状态和 events
kubectl get events -n default --sort-by=.lastTimestamp  # 看事件
kubectl logs order-service -n default              # 看日志
kubectl describe node                              # 看节点资源
```

排查过程依赖经验，不同运维人员的排查深度和效率差异大。

### 1.2 目标

构建一个**对话式 AI 智能体**：

- 用户用自然语言描述问题（如 "排查 order-service Pod 启动失败"）
- 智能体自主决定执行哪些 kubectl 命令，逐步收敛根因
- **全程记录排查思维链**，用户可随时查看推理过程
- 输出结构化诊断报告（症状 → 根因 → 证据 → 修复建议）
- **只读操作**，不修改集群状态

---

## 二、核心设计原则

| 原则 | 说明 |
|------|------|
| **kubectl 驱动** | 智能体的每个工具 = 一条 kubectl 命令。排查过程 = 真实命令流，运维可直接复用 |
| **思维链可观测** | 每一步推理（观察→假设→验证→结论）结构化记录，用户可见 |
| **默认只读** | 权限默认 read-only，可配置放宽，代码层命令白名单 + 关键字黑名单强制校验 |
| **渐进式诊断** | LLM 根据每次 kubectl 返回决定下一步，不一次性 dump 所有信息 |
| **知识增强** | TF-IDF 检索相关知识库，注入 LLM 上下文辅助诊断 |

---

## 三、技术实现

### 3.1 技术栈

| 组件 | 实现 |
|------|------|
| LLM API | 原生 OpenAI API (async) |
| Agent 模式 | 原生 ReAct 循环实现 |
| 工具调用 | OpenAI Function Calling |
| 配置管理 | Pydantic + YAML |
| CLI | Typer |
| 知识检索 | TF-IDF (纯 Python，无向量数据库) |

---

## 四、功能需求

### 4.1 诊断场景覆盖

| 场景 | Pod 状态 | 典型原因 |
|------|----------|----------|
| 镜像拉取失败 | Waiting / ImagePullBackOff | 镜像不存在、认证失败、注册表不可达 |
| 容器反复崩溃 | Waiting / CrashLoopBackOff | 应用启动失败、配置缺失、健康检查失败 |
| 内存溢出 | Terminated / OOMKilled | 超过 memory limit |
| 调度失败 | Pending / FailedScheduling | 资源不足、Taint/Toleration、亲和性不匹配 |
| 健康检查失败 | Running / Unhealthy | liveness/readiness probe 配置错误 |
| 配置引用失败 | Waiting / CreateContainerConfigError | ConfigMap/Secret 不存在 |
| **CNI 网络异常** | Pending / Running 但网络不通 | CNI 插件未就绪、IP 池耗尽、NetworkPolicy 阻断 |
| **Volcano 调度失败** | Pending / Gang-Scheduling 死锁 | PodGroup 未满足、Queue 资源不足、Gang 最小成员数无法达成 |

### 4.2 能力清单

| 能力 | 说明 |
|------|------|
| 自然语言理解 | 从用户描述中识别 namespace、资源类型、资源名 |
| 自主决策排查路径 | 根据 kubectl 返回结果动态决定下一步查什么 |
| 思维链追踪 | 记录 observation → hypothesis → verification → conclusion |
| 上下文压缩 | 可选压缩思维链，减少 token 使用量 |
| 结构化报告输出 | 症状 + 根因 + 证据 + 修复命令 |
| 命令审计日志 | 记录所有执行过的 kubectl 命令 |
| 权限模式切换 | read-only / diagnostic / read-write 三级 |
| 交互式排查 | 支持对话式追问 |
| **CNI 网络排查** | 覆盖 CNI 插件状态、Pod IP 分配、NetworkPolicy、DNS、跨节点连通性 |
| **Volcano 调度排查** | 覆盖 PodGroup、Queue、VCJob、Gang Scheduling、调度器配置 |
| **知识库检索** | TF-IDF 检索相关知识文档，注入 LLM 上下文 |

---

## 五、配置系统

### 5.1 配置层级

```
默认值 → 环境变量 → 配置文件 → CLI 参数
```

### 5.2 配置项

```yaml
llm:
  provider: str = "openai"         # LLM 提供商
  model: str = "gpt-4o"            # 模型名称
  temperature: float = 0.1          # 温度参数
  api_key: str = ""                # API 密钥
  base_url: str = ""               # 自定义 API 地址

k8s:
  kubeconfig: str | None = None     # kubeconfig 路径
  default_namespace: str = "default"
  mode: str = "read-only"           # read-only | diagnostic | read-write
  bypass_blacklist: bool = false    # 绕过黑名单（需 read-write 模式）

agent:
  max_tool_calls: int = 20          # 最大工具调用次数
  timeout_seconds: int = 120        # 单次诊断超时
  show_thoughts: bool = true        # 显示思维链
  context_compression: bool = true  # 启用上下文压缩

knowledge:
  enabled: bool = true              # 启用知识库
  knowledge_dir: str = "knowledge"  # 知识库目录
  max_results: int = 3              # 最大检索结果数
  min_score: float = 0.01           # 最小相关性分数
  max_injected_chars: int = 4000    # 最大注入字符数
```

---

## 六、安全与约束

| 约束 | 说明 |
|------|------|
| 命令白名单 | 只允许子命令白名单内的操作（get/describe/logs 等），非白名单直接拒绝 |
| 防注入 | 禁止 shell 元字符（`\|`, `;`, `$`, `` ` ``） |
| 敏感参数拦截 | 禁止 `--kubeconfig`, `--server`, `--token`, `--certificate-authority`, `--as`, `--as-group` |
| 关键字黑名单 | 命令参数中匹配危险关键字时拒绝执行 |
| 默认只读 | `--mode` 默认 read-only |
| 审计日志 | 所有命令记录到日志 |
| 超时保护 | subprocess timeout 30s, max_tool_calls=20 |

### 6.1 关键字黑名单

黑名单机制在子命令白名单之上，对命令参数做二次校验，拦截包含危险关键字的参数。

| 黑名单关键字 | 拦截原因 | 示例 |
|-------------|---------|------|
| `delete` | 删除资源 | `kubectl delete pod xxx` |
| `patch` | 修改资源配置 | `kubectl patch deployment xxx` |
| `scale` | 修改副本数 | `kubectl scale deploy xxx --replicas=0` |
| `cordon` | 节点不可调度 | `kubectl cordon node1` |
| `drain` | 驱逐节点 Pod | `kubectl drain node1` |
| `taint` | 节点加污点 | `kubectl taint node1 key=value` |
| `--force` | 强制删除 | `kubectl delete pod xxx --force` |
| `--grace-period=0` | 立即终止 | `kubectl delete pod xxx --grace-period=0` |

黑名单在 `diagnostic` 模式下也生效（即使 `diagnostic` 模式允许 `exec` 和 `cp`，上述黑名单参数仍被拒绝）。`read-write` 模式下黑名单降级为警告（warning 日志但放行），需 `--mode read-write` 配合配置项 `bypass_blacklist: true` 才放开。

---

## 七、诊断示例

### 场景 1: ImagePullBackOff

**输入**：
```
$ k8s-diagnose --show-thoughts "排查 default 下 order-service Pod 启动失败"
```

**思维链**：
```
👁 [observation] Pod order-service Phase=Pending, 容器 Waiting
💡 [hypothesis] 容器 Waiting，可能是镜像拉取失败
⚡ [action] kubectl describe pod order-service -n default
👁 [observation] Events: "Failed to pull image: unauthorized"
🔍 [verification] kubectl get pod order-service -o yaml → 未配置 imagePullSecrets
✅ [conclusion] 镜像仓库认证失败 — registry.internal 需要认证
```

**诊断报告**：
```markdown
## 症状
Pod order-service Pending，容器 Waiting (ImagePullBackOff)

## 根因
镜像 registry.internal/order-service:v2.3.1 拉取失败，返回 unauthorized。
Pod 未配置 imagePullSecrets。

## 证据
- Events: "Failed to pull image... unauthorized"
- imagePullSecrets: 未配置

## 修复
kubectl create secret docker-registry regcred \
  --docker-server=registry.internal --docker-username=<u> --docker-password=<p>
kubectl patch serviceaccount default -p \
  '{"imagePullSecrets":[{"name":"regcred"}]}'
```

### 场景 2: Volcano Gang Scheduling 死锁

**输入**：
```
$ k8s-diagnose -n training "排查 ml-training-job 调度失败"
```

**思维链**：
```
👁 [observation] Pod ml-training-job-worker-0 Phase=Pending
💡 [hypothesis] 使用 Volcano 的 ML 训练任务，可能是 Gang Scheduling 未满足
⚡ [action] kubectl get podgroup -n training
👁 [observation] PodGroup ml-training-job: minAvailable=8, active=3
💡 [hypothesis] Gang 要求 8 个 Pod 同时启动，当前只调度了 3 个，剩余 5 个资源不足
⚡ [action] kubectl describe podgroup ml-training-job -n training
👁 [observation] Events: "3 of 8 tasks in Gang unschedulable: 0/5 nodes: Insufficient nvidia.com/gpu"
⚡ [action] kubectl get nodes -o wide (查看 GPU 资源)
👁 [observation] 5 个节点中 3 个 GPU 已用完，2 个 GPU 不足（需要每节点 1 张卡）
✅ [conclusion] 集群 GPU 资源不足，无法同时满足 PodGroup 的 8 卡 Gang 调度需求
```

### 场景 3: CNI 网络异常导致 Pod 不通

**输入**：
```
$ k8s-diagnose -n production "排查后端服务无法访问数据库"
```

**思维链**：
```
👁 [observation] 后端 Pod Running，数据库 Pod Running，但网络不通
💡 [hypothesis] 两个 Pod 都 Running，问题可能在网络层（CNI/NetworkPolicy/Service）
⚡ [action] kubectl get networkpolicy -n production
👁 [observation] 存在 NetworkPolicy "deny-all-ingress" 阻断了所有入站流量
✅ [conclusion] NetworkPolicy 规则过严，未放行后端 Pod 到数据库端口的流量
```

---

## 八、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | 单次诊断应在 120 秒内完成，最多 20 次工具调用 |
| 可用性 | 无 K8s 集群时，可通过 mock kubectl 输出进行测试 |
| 可观测性 | 思维链和命令审计日志可导出 |
| 兼容性 | 支持标准 K8s + CNI（Calico/Cilium/Flannel）+ Volcano |
| 权限最小化 | 默认只读，放宽需显式参数 + 黑名单确认 |

---

## 九、已知限制与未来规划

### 9.1 已知限制

1. **CNI/Volcano 分析器**：目前仅有 PodAnalyzer 和 SchedulerAnalyzer，CNI 和 Volcano 专项分析器暂未实现，相关诊断通过 Agent 直接调用专用工具完成
2. **单次会话**：目前不支持跨会话记忆
3. **只读限制**：默认模式下无法执行 exec/cp 等需要深入容器排查的操作

### 9.2 未来规划

1. 实现 CNIAnalyzer 和 VolcanoAnalyzer 专项分析器
2. 支持多轮对话上下文保持
3. 添加更多知识库文档（Storage、RBAC、Ingress 等场景）
