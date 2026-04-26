---
id: E016
title: "调度失败 - 资源不足"
category: scheduling
description: "节点资源（CPU/内存/GPU）不足以满足 Pod 请求"
symptoms:
  - "0/X nodes are available: Insufficient cpu"
  - "0/X nodes are available: Insufficient memory"
  - "0/X nodes are available: Insufficient nvidia.com/gpu"
severity: high
---

# 调度失败 - 资源不足

## 症状表现

- Pod 状态 `Pending`
- `kubectl describe pod` 显示资源不足
- Events: `FailedScheduling`

## 排查步骤

### 1. 查看调度失败原因

```bash
kubectl describe pod <pod-name> | grep -A5 "Events"
```

**关键信息**:
```
Warning  FailedScheduling  5m  default-scheduler  
0/3 nodes are available: 
1 Insufficient memory, 
2 Insufficient cpu.
```

### 2. 检查 Pod 资源请求

```bash
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].resources}'
```

**示例**:
```yaml
resources:
  requests:
    cpu: "4"
    memory: 8Gi
```

### 3. 检查节点可分配资源

```bash
# 查看所有节点资源
kubectl top nodes

# 查看节点详情
kubectl describe node <node-name>
```

**关注 Allocatable 和 Allocated**:
```
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests      Limits
  --------           --------      ------
  cpu                2850m (71%)   3100m (77%)
  memory             6144Mi (76%)  8192Mi (102%)
```

### 4. 计算资源缺口

```bash
# 查看节点剩余可分配资源
kubectl get node <node-name> -o jsonpath='{.status.allocatable}' | jq .

# 计算已使用
kubectl get pods --all-namespaces -o json | \
  jq --arg node "<node-name>" '[.items[] | select(.spec.nodeName == $node)] | map(.spec.containers[].resources.requests.cpu // 0) | add'
```

## 常见原因与解决方案

### 原因 1: CPU 不足

**症状**: `Insufficient cpu`

**解决方案**:
1. 降低 Pod CPU request
2. 扩容节点数量
3. 升级节点 CPU 配置
4. 使用 CPU 超卖（需谨慎）

```yaml
resources:
  requests:
    cpu: "500m"    # 从 2000m 降低
  limits:
    cpu: "2000m"
```

### 原因 2: 内存不足

**症状**: `Insufficient memory`

**解决方案**:
1. 降低 memory request
2. 扩容节点
3. 清理节点上的非必要 Pod

**注意**: 内存不能像 CPU 一样压缩，必须实际分配

### 原因 3: GPU 不足

**症状**: `Insufficient nvidia.com/gpu`

**排查**:
```bash
# 查看节点 GPU 状态
kubectl describe node <node-name> | grep nvidia.com/gpu

# 查看 GPU 已分配
kubectl get pods --all-namespaces -o custom-columns='NAME:.metadata.name,GPU:.spec.containers[*].resources.requests.nvidia\.com/gpu'
```

**解决方案**:
- 等待 GPU Pod 完成
- 增加 GPU 节点
- 使用 GPU 共享（如 vGPU、MIG）

### 原因 4: 临时存储不足

**症状**: `Insufficient ephemeral-storage`

**解决方案**:
```yaml
resources:
  requests:
    ephemeral-storage: "1Gi"
  limits:
    ephemeral-storage: "2Gi"
```

### 原因 5: Pod 过多导致端口耗尽

**症状**: `Insufficient ports`

**排查**: HostPort 冲突

```bash
kubectl get pods --all-namespaces -o json | \
  jq '.items[].spec.containers[].ports[]? | select(.hostPort) | {hostPort, protocol}'
```

## 资源优化建议

### 合理设置 Request

```yaml
resources:
  requests:
    cpu: "100m"      # 基于实际使用设置
    memory: "128Mi"  # 必须能满足启动需求
  limits:
    cpu: "1000m"     # 可设置较大，允许突发
    memory: "512Mi"  # 防止 OOM
```

### 使用 LimitRange

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
spec:
  limits:
  - default:
      cpu: "500m"
      memory: "256Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    type: Container
```

### 使用 ResourceQuota

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: namespace-quota
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
```

## 诊断命令速查

```bash
# 查看所有 Pending Pod
kubectl get pods --all-namespaces | grep Pending

# 查看资源不足导致的 Pending
kubectl get events --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'

# 节点资源使用排名
kubectl top nodes --sort-by=cpu
kubectl top nodes --sort-by=memory

# 找出高资源使用 Pod
kubectl top pods --all-namespaces --sort-by=cpu | head -20
```

## 参考链接

- [Kubernetes Scheduling](https://kubernetes.io/docs/concepts/scheduling-eviction/)
- [Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
