---
id: E014
title: "Init 容器失败"
category: pod
description: "Init Container 无法正常完成初始化"
symptoms:
  - "Pod 状态 Init:Error"
  - "Init 容器反复重启"
  - "Pod 卡在 Init 阶段"
severity: high
---

# Init Container 失败

## 症状表现

- Pod 状态显示 `Init:Error` 或 `Init:CrashLoopBackOff`
- Pod 一直卡在 `Init:0/X`
- 主容器未启动

## 排查步骤

### 1. 查看 Init 容器状态

```bash
# 查看 Pod 状态
kubectl get pod <pod-name>

# 查看详情
kubectl describe pod <pod-name>
```

**状态说明**:
- `Init:0/1` - 第 1 个 Init 容器正在运行
- `Init:Error` - Init 容器执行失败
- `Init:CrashLoopBackOff` - Init 容器反复崩溃

### 2. 查看 Init 容器日志

```bash
# 查看特定 Init 容器日志
kubectl logs <pod-name> -c <init-container-name>

# 查看失败的 Init 容器日志（如果已退出）
kubectl logs <pod-name> -c <init-container-name> --previous
```

### 3. 检查 Init 容器配置

```bash
kubectl get pod <pod-name> -o yaml | grep -A20 "initContainers"
```

## 常见原因与解决方案

### 原因 1: 命令执行失败

**症状**: Init 容器 Exit Code 非 0

**排查**:
```bash
kubectl describe pod <pod-name> | grep -A5 "State:"
```

**示例输出**:
```
Init Containers:
  init-myservice:
    State:          Waiting
    Reason:         CrashLoopBackOff
    Last State:     Terminated
    Reason:         Error
    Exit Code:      1
```

**解决方案**: 修正 Init 容器命令或脚本

### 原因 2: 网络/服务依赖未就绪

**症状**: 等待外部服务超时

**常见场景**:
- 等待数据库启动
- 等待配置中心可用
- 等待其他 Service Ready

**解决方案**:
```yaml
initContainers:
- name: wait-for-service
  image: busybox:1.28
  command:
  - sh
  - -c
  - |
    until nc -z my-service 3306; do
      echo "Waiting for my-service..."
      sleep 2
    done
```

### 原因 3: 权限不足

**症状**: Permission denied

**解决方案**:
```yaml
initContainers:
- name: init-permissions
  image: busybox:1.28
  command: ['sh', '-c', 'chmod 755 /app/data']
  securityContext:
    runAsUser: 0  # 以 root 运行
```

### 原因 4: 资源限制

**症状**: Init 容器被 OOMKilled 或 CPU throttle

**解决方案**: 为 Init 容器单独配置 resources

```yaml
initContainers:
- name: init-db
  image: mysql:8.0
  command: ['sh', '-c', 'mysql -h db -e "CREATE DATABASE IF NOT EXISTS app"']
  resources:
    limits:
      memory: "256Mi"
      cpu: "500m"
```

### 原因 5: Init 容器顺序依赖

**症状**: 多个 Init 容器，前面的失败导致后续无法执行

**排查**: Init 容器按定义顺序串行执行

**解决方案**: 确保 Init 容器设计为幂等，可重复执行

## Init 容器 vs Sidecar

| 特性 | Init Container | Sidecar |
|------|----------------|---------|
| 执行顺序 | Pod 启动前串行执行 | 与主容器并行运行 |
| 数量 | 可有多个 | 可有多个 |
| 生命周期 | 完成后退出 | 与 Pod 同生命周期 |
| 用途 | 初始化、等待依赖 | 辅助功能（日志、监控等）|

## 诊断命令速查

```bash
# 查看 Init 容器列表
kubectl get pod <pod-name> -o jsonpath='{.spec.initContainers[*].name}'

# 查看 Init 容器状态
kubectl get pod <pod-name> -o jsonpath='{.status.initContainerStatuses}' | jq .

# 快速诊断脚本
kubectl get pods --all-namespaces | grep -E "Init:" | \
  awk '{print $1 " " $2}' | while read ns pod; do
    echo "=== $ns/$pod ==="
    kubectl logs $pod -n $ns --previous 2>/dev/null | tail -5
  done
```

## 参考链接

- [Understanding Init Containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)
- [Debug Init Containers](https://kubernetes.io/docs/tasks/debug/debug-application/debug-init-containers/)
