---
title: "K8s 故障排查总览"
description: "系统化的 Kubernetes 故障排查方法和流程"
category: runbook
date: 2026-04-26
---

# K8s 故障排查总览

## 排查原则

1. **分层排查**：集群 → 节点 → Pod → 容器 → 应用
2. **由外到内**：先检查外部依赖，再检查内部状态
3. **日志为证**：不猜测，看日志和事件

## 快速诊断流程

### Step 1: 定位问题范围

```bash
# 查看集群整体状态
kubectl get nodes
kubectl cluster-info

# 查看问题 Pod
kubectl get pods --all-namespaces -o wide
```

### Step 2: 查看 Pod 状态

```bash
kubectl get pod <pod-name> -o yaml | grep -A5 "phase\|containerStatuses"
```

| 状态 | 含义 | 下一步 |
|------|------|--------|
| Pending | 未调度或拉取镜像 | 查看 Events |
| Running | 运行中 | 检查应用日志 |
| Succeeded | 完成 | 检查退出码 |
| Failed | 失败 | 查看 logs --previous |
| Unknown | 状态未知 | 检查节点 |
| CrashLoopBackOff | 反复崩溃 | 查看日志 |
| ImagePullBackOff | 镜像拉取失败 | 检查镜像配置 |
| Evicted | 被驱逐 | 查看节点资源 |

### Step 3: 查看事件

```bash
# 按时间排序查看事件
kubectl get events --sort-by='.lastTimestamp' | tail -20

# 查看特定 Pod 事件
kubectl get events --field-selector involvedObject.name=<pod-name>

# 查看警告事件
kubectl get events --field-selector type=Warning
```

### Step 4: 查看日志

```bash
# 实时日志
kubectl logs -f <pod-name>

# 之前失败的日志
kubectl logs <pod-name> --previous

# 多容器 Pod
kubectl logs <pod-name> -c <container-name>

# 带时间戳
kubectl logs <pod-name> --timestamps
```

## 常见故障速查表

### Pod 启动问题

| 现象 | 可能原因 | 排查命令 |
|------|----------|----------|
| Pending | 资源不足/调度约束 | `describe pod` |
| ImagePullBackOff | 镜像不存在/认证失败 | `describe pod` |
| CrashLoopBackOff | 应用崩溃/健康检查失败 | `logs --previous` |
| Init:Error | Init 容器失败 | `logs -c init-container` |

### 运行时问题

| 现象 | 可能原因 | 排查命令 |
|------|----------|----------|
| OOMKilled | 内存超限 | `describe pod` 看 Exit Code 137 |
| Evicted | 节点资源压力 | `describe node` |
| Unhealthy | 探针失败 | `describe pod` 看 Events |
| Terminating | 删除中卡住 | `describe pod` 看 Finalizers |

### 网络问题

| 现象 | 可能原因 | 排查命令 |
|------|----------|----------|
| 无 ClusterIP | kube-proxy 异常 | `kubectl get svc` |
| DNS 失败 | CoreDNS 异常 | `nslookup` from Pod |
| 跨节点不通 | CNI 问题 | 检查 CNI Pod |
| 特定服务不通 | NetworkPolicy | `describe networkpolicy` |

## 常用诊断命令

```bash
# 一键查看 Pod 状态
kubectl get pods -o custom-columns='NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,NODE:.spec.nodeName'

# 查看资源使用
kubectl top nodes
kubectl top pods --all-namespaces

# 查看节点详细状态
kubectl describe node <node-name>

# 查看所有 Warning 事件
kubectl get events --field-selector type=Warning --sort-by='.lastTimestamp'
```

## 参考资料

- [Kubernetes Troubleshooting Official Guide](https://kubernetes.io/docs/tasks/debug/)
- [kubectl Cheat Sheet](https://kubernetes.io/docs/reference/kubectl/cheatsheet/)
