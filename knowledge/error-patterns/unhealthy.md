---
id: E013
title: "健康检查失败"
category: pod
description: "Liveness 或 Readiness Probe 持续失败"
symptoms:
  - "Pod 频繁重启"
  - "Service 无后端可用"
  - "Unhealthy 事件"
  - "Readiness probe failed 日志"
severity: medium
---

# 健康检查失败 (Liveness/Readiness Probe)

## 症状表现

- Pod 频繁重启（Liveness 失败）
- Service 无可用 Endpoints（Readiness 失败）
- `kubectl describe pod` 显示 probe 失败
- Events 中出现 `Unhealthy` 警告

## 排查步骤

### 1. 查看 Probe 配置

```bash
kubectl get pod <pod-name> -o yaml | grep -A30 "livenessProbe\|readinessProbe"
```

**关键字段**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

### 2. 查看 Probe 失败详情

```bash
kubectl describe pod <pod-name>
```

**Events 关键信息**:
```
Warning  Unhealthy  5m  kubelet  Liveness probe failed: HTTP probe failed with statuscode: 500
Warning  Unhealthy  4m  kubelet  Readiness probe failed: Get "http://10.244.1.5:8080/ready": connection refused
```

### 3. 手动测试 Probe 端点

```bash
# 进入 Pod
kubectl exec -it <pod-name> -- sh

# 测试健康检查端点
curl -v http://localhost:8080/healthz
curl -v http://localhost:8080/ready

# 检查端口监听
netstat -tlnp | grep 8080
ss -tlnp | grep 8080
```

### 4. 查看应用日志

```bash
# 查看容器日志
kubectl logs <pod-name>

# 查看上一次重启前的日志
kubectl logs <pod-name> --previous

# 查看特定时间段的日志
kubectl logs <pod-name> --since=10m
```

## 常见原因与解决方案

### 原因 1: 端口配置错误

**症状**: `connection refused`

**排查**:
```bash
# 检查应用实际监听端口
kubectl exec <pod-name> -- netstat -tlnp
```

**解决方案**: 修正 probe 配置中的 port

### 原因 2: Path 配置错误

**症状**: `HTTP probe failed with statuscode: 404`

**解决方案**: 确认应用实际的健康检查路径

### 原因 3: 启动时间过长

**症状**: 应用启动期间被误杀

**解决方案**: 增加 `initialDelaySeconds` 或 `startupProbe`

```yaml
startupProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
  failureThreshold: 12  # 10s + 12*5s = 70s 启动时间
```

### 原因 4: 应用启动慢/依赖未就绪

**症状**: 数据库/缓存未连接时健康检查失败

**解决方案**:
```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5
```

### 原因 5: 资源不足导致响应慢

**症状**: `timeout`，CPU throttling

**排查**:
```bash
kubectl top pod <pod-name>
kubectl describe pod <pod-name> | grep -i throttle
```

**解决方案**: 增加 CPU limit

### 原因 6: Exec Probe 命令问题

**症状**: 使用 exec probe 时失败

**排查**:
```bash
# 在 Pod 内测试命令
kubectl exec <pod-name> -- <probe-command>
```

**常见问题**:
- 命令不存在
- 权限不足
- 命令执行时间过长（超过 `timeoutSeconds`）

## Probe 类型对比

| 类型 | 适用场景 | 示例 |
|------|----------|------|
| httpGet | Web 应用 | `path: /healthz, port: 8080` |
| tcpSocket | TCP 服务 | `port: 3306` |
| exec | 自定义检查 | `command: ["cat", "/tmp/healthy"]` |
| grpc | gRPC 服务 | `port: 50051` |

## Probe 配置最佳实践

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    # Startup Probe - 防止启动慢被误杀
    startupProbe:
      httpGet:
        path: /healthz
        port: 8080
      initialDelaySeconds: 10
      periodSeconds: 5
      failureThreshold: 30  # 最多允许 150s 启动
    
    # Liveness Probe - 检测应用存活
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 5
      failureThreshold: 3
    
    # Readiness Probe - 检测是否可接受流量
    readinessProbe:
      httpGet:
        path: /ready
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 3
      failureThreshold: 3
      successThreshold: 1  # 成功后立即标记为 Ready
```

## 诊断命令速查

```bash
# 查看所有 Unhealthy Pod
kubectl get pods --all-namespaces -o json | \
  jq '.items[] | select(.status.conditions[]? | select(.type == "Ready" and .status == "False")) | {name: .metadata.name, ns: .metadata.namespace}'

# 查看 probe 配置
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].livenessProbe}'
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].readinessProbe}'

# 查看 probe 失败事件
kubectl get events --field-selector reason=Unhealthy --sort-by='.lastTimestamp'
```

## 参考链接

- [Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
