# k8s-diagnose — K8s 运维诊断智能体

对话式 AI 智能体，排查 K8s Pod 启动失败、调度失败、CNI 网络异常、Volcano 调度问题等根因。

## 快速开始

```bash
# 安装
pip install -e .

# 单次诊断（自动查找 namespace）
k8s-diagnose "排查 order-service Pod 启动失败"

# 指定 namespace
k8s-diagnose -n kube-system "排查 coredns 启动失败"

# 交互模式
k8s-diagnose -i

# 显示思维链（默认开启）
k8s-diagnose --show-thoughts "排查 xxx"

# 使用配置文件
k8s-diagnose --config config.yaml "排查 xxx"
```

## 诊断场景

| 场景 | 说明 |
|------|------|
| ImagePullBackOff | 镜像拉取失败 |
| CrashLoopBackOff | 容器反复崩溃 |
| OOMKilled | 内存溢出 |
| FailedScheduling | 调度失败 |
| Unhealthy | 健康检查失败 |
| CNI 网络异常 | 网络插件/NetworkPolicy/DNS |
| Volcano 调度失败 | PodGroup/Gang Scheduling |

## 特性

- **自动查找 namespace**: 未指定 `-n` 时，自动在所有 namespace 中查找匹配的 Pod
- **思维链可观测**: 实时显示排查推理过程
- **知识增强**: 基于知识库的 RAG 诊断建议
- **多层安全防护**: 白名单 + 黑名单 + Shell 注入防护

## CLI 参数

```
参数:
  QUERY           诊断问题描述 [required]

选项:
  -n, --namespace TEXT       K8s 命名空间 [default: 自动查找]
  --mode TEXT                权限模式: read-only | diagnostic | read-write [default: read-only]
  --kubeconfig TEXT          kubeconfig 路径
  --show-thoughts / --no-thoughts  显示排查思维链 [default: show-thoughts]
  -i, --interactive          交互模式
  --config TEXT              配置文件路径 (YAML)
  --help                     显示帮助信息
```

## 配置文件

复制 `config.yaml.example` 为 `config.yaml` 并修改：

```yaml
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.1
  api_key: ""           # 或从环境变量 OPENAI_API_KEY 读取
  base_url: ""          # 自定义 API 地址

k8s:
  kubeconfig: null      # 默认使用 ~/.kube/config
  default_namespace: default    # 未指定时的默认 namespace
  mode: read-only       # read-only | diagnostic | read-write

agent:
  max_tool_calls: 20
  timeout_seconds: 120
  show_thoughts: true
  context_compression: true

knowledge:
  enabled: true
  knowledge_dir: knowledge
  max_results: 3
```

## 安全

- 默认只读模式，只允许 get/describe/logs 等只读命令
- 子命令白名单 + 关键字黑名单双重防护
- Shell 注入防护（禁止 `|`, `;`, `$`, `` ` `` 等字符）
- 敏感参数拦截（禁止 `--kubeconfig`, `--server`, `--token` 等）

## 文档

- [需求文档](REQUIREMENTS.md)
- [架构设计](ARCHITECTURE.md)
