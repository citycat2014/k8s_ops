---
id: E011
title: "OOMKilled"
category: pod
description: "Pod 因内存不足被系统杀掉"
symptoms:
  - "Pod 状态 OOMKilled"
  - "Exit Code 137"
  - "容器频繁重启"
  - "内存监控告警"
severity: high
---

# OOMKilled (内存溢出)

## 症状表现

- Pod 状态显示 `OOMKilled`
- `kubectl describe pod` 显示 `Reason: OOMKilled`
- 容器 Exit Code: 137 (128 + 9 SIGKILL)
- 应用日志突然中断，无正常关闭日志

## 排查步骤

### 1. 确认 OOM 事件

```bash
# 查看 Pod 状态
kubectl get pod <pod-name> -o yaml | grep -A10 "containerStatuses"

# 关键字段
state:
  terminated:
    reason: OOMKilled
    exitCode: 137
    finishedAt: "2024-01-15T10:30:00Z"
```

### 2. 查看 Pod 内存配置

```bash
kubectl get pod <pod-name> -o yaml | grep -A20 "resources"
```

**关注字段**:
- `resources.limits.memory` - 内存硬限制
- `resources.requests.memory` - 内存请求（调度用）

**判断逻辑**:
- 无 limit → Pod 可能使用节点全部内存，导致节点级 OOM
- limit 设置过低 → 应用实际内存需求超过限制

### 3. 检查历史内存使用

```bash
# 查看 Pod 内存使用历史（需 metrics-server）
kubectl top pod <pod-name>

# 查看容器内存使用
kubectl top pod <pod-name> --containers

# 查看更详细的监控（如有 Prometheus）
# container_memory_working_set_bytes / container_spec_memory_limit_bytes
```

### 4. 分析应用内存使用

```bash
# 进入运行中的 Pod（如果还能运行）
kubectl exec -it <pod-name> -- sh

# 查看进程内存使用
top
free -m
ps aux --sort=-%mem | head

# Java 应用查看 JVM 内存
jmap -heap <pid>
jstat -gc <pid>
```

### 5. 检查节点内存压力

```bash
# 查看节点内存状况
kubectl describe node <node-name> | grep -A10 "MemoryPressure"

# 查看节点内存分配
kubectl get node <node-name> -o yaml | grep -A5 "allocatable"

# 查看节点上的 Pod 内存使用情况
kubectl top pod --all-namespaces | grep <node-name>
```

## 常见原因与解决方案

### 原因 1: Limit 设置过低

**症状**: 应用内存需求正常，但超过 limit 被 kill

**解决方案**:
```yaml
resources:
  limits:
    memory: "512Mi"    # 增加 limit
  requests:
    memory: "256Mi"
```

### 原因 2: 内存泄漏

**症状**: 内存使用持续增长，最终被 OOM

**排查**:
- 检查应用代码内存泄漏
- 检查是否有未关闭的连接/文件句柄
- 检查缓存是否无限增长

**解决方案**: 修复应用代码，或添加重启策略

### 原因 3: 无 Limit 导致节点 OOM

**症状**: Pod 无 memory limit，使用过多内存导致节点触发 OOM killer

**解决方案**: 始终为 Pod 设置 memory limit

### 原因 4: 突发流量/大数据处理

**症状**: 特定场景下内存飙升（如批量处理大文件）

**解决方案**:
- 分批处理数据
- 使用临时增加 limit 的 Job
- 水平扩容分散压力

### 原因 5: Sidecar 容器 OOM

**症状**: 业务容器正常，但 Sidecar（如 Istio proxy）被 OOM

**解决方案**: 为 Sidecar 单独配置 limit

## 预防措施

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            memory: "256Mi"    # 基于正常运行内存设置
          limits:
            memory: "512Mi"    # 预留 2x 余量
        # 添加监控告警
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
```

## 诊断命令速查

```bash
# 快速查看 OOM Pod
kubectl get pods --all-namespaces -o json | \
  jq '.items[] | select(.status.containerStatuses[]?.state.terminated?.reason == "OOMKilled") | {name: .metadata.name, namespace: .metadata.namespace}'

# 查看 Pod OOM 次数
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].restartCount}'

# 查看节点 OOM 事件
kubectl get events --field-selector reason=OOMKilled --sort-by='.lastTimestamp'
```

## 参考链接

- [Sysdig - OOMKilled Troubleshooting](https://sysdig.com/blog/troubleshoot-oomkilled/)
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
