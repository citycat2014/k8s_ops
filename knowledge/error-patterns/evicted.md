---
id: E012
title: "Evicted"
category: pod
description: "Pod 因节点资源压力被驱逐"
symptoms:
  - "Pod 状态 Evicted"
  - "Pod 被重新调度到其他节点"
  - "节点磁盘/内存压力"
severity: medium
---

# Pod Evicted (节点压力驱逐)

## 症状表现

- Pod 状态显示 `Evicted`
- Pod 被终止并在其他节点重新创建
- `kubectl describe pod` 显示驱逐原因
- 节点存在 DiskPressure / MemoryPressure / PIDPressure 污点

## 排查步骤

### 1. 确认驱逐原因

```bash
# 查看被驱逐的 Pod
kubectl get pods --all-namespaces | grep Evicted

# 查看驱逐详情
kubectl describe pod <pod-name>
```

**关键信息**（Events 部分）:
```
The node was low on resource: memory.
Container xxx was using 800Mi, which exceeds its request of 512Mi.
```

### 2. 检查节点压力状况

```bash
# 查看节点状态
kubectl get nodes -o wide

# 查看节点详情
kubectl describe node <node-name>
```

**关注 Conditions**:
- `MemoryPressure: True` - 内存压力
- `DiskPressure: True` - 磁盘压力
- `PIDPressure: True` - 进程数压力
- `Ready: False` - 节点不健康

### 3. 检查节点资源使用

```bash
# 在节点上执行（或通过 kubectl debug node）
df -h                    # 检查磁盘使用
free -h                  # 检查内存使用
ps aux | wc -l           # 检查进程数
du -sh /var/lib/docker   # 检查容器存储占用
du -sh /var/log          # 检查日志占用
```

## 常见原因与解决方案

### 原因 1: 磁盘压力 (DiskPressure)

**触发条件**: 磁盘使用超过 85% 或 inode 使用超过 95%

**常见场景**:
- 容器日志未轮转，无限增长
- 镜像缓存占用过多空间
- EmptyDir 未清理
- 临时文件堆积

**解决方案**:
```bash
# 清理已停止的容器
docker system prune -a

# 清理未使用的镜像
docker image prune -a

# 配置日志轮转
# /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "5"
  }
}

# K8s 层面配置容器日志限制
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    resources:
      ephemeral-storage: "1Gi"    # 限制临时存储
```

### 原因 2: 内存压力 (MemoryPressure)

**触发条件**: 节点内存使用过高

**解决方案**:
- 为所有 Pod 设置 memory limit
- 降低节点上运行的 Pod 数量
- 升级节点内存配置
- 使用 Pod Priority 和 Preemption

### 原因 3: 进程压力 (PIDPressure)

**触发条件**: 节点进程数过多

**常见场景**:
- 应用创建大量线程/子进程
- 僵尸进程堆积

**解决方案**:
```yaml
# 设置 Pod PID 限制
apiVersion: v1
kind: Pod
spec:
  securityContext:
    sysctls:
    - name: kernel.pid_max
      value: "65536"
```

## 驱逐优先级

Kubelet 驱逐 Pod 时遵循以下优先级：

1. **BestEffort** (无 request/limit) - 最先被驱逐
2. **Burstable** (request < limit) - 根据资源使用超出 request 的比例
3. **Guaranteed** (request = limit) - 最后被驱逐

## 预防措施

```yaml
# 配置资源请求和限制
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: app
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
            ephemeral-storage: "1Gi"
          limits:
            memory: "512Mi"
            cpu: "500m"
            ephemeral-storage: "2Gi"
      # 配置容忍，允许调度到有压力的节点
      tolerations:
      - key: "node.kubernetes.io/memory-pressure"
        operator: "Exists"
        effect: "NoSchedule"
```

## 清理被驱逐的 Pod

```bash
# 删除所有被驱逐的 Pod
kubectl get pods --all-namespaces | grep Evicted | \
  awk '{print $2 " -n " $1}' | xargs -L1 kubectl delete pod

# 或使用脚本
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.status.reason == "Evicted") | .metadata.name + " -n " + .metadata.namespace' | \
  xargs -L1 kubectl delete pod
```

## 监控告警建议

```yaml
# Prometheus 告警规则
- alert: NodeDiskPressure
  expr: node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Node {{ $labels.instance }} disk pressure"
    
- alert: NodeMemoryPressure
  expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.85
  for: 5m
  labels:
    severity: critical
```

## 参考链接

- [Kubernetes Eviction Policy](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)
- [Configuring Garbage Collection](https://kubernetes.io/docs/concepts/architecture/garbage-collection/)
