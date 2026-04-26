---
id: kb-pod-diagnosis
title: Pod 故障排查标准流程
type: runbook
scope: pod
complexity: beginner
---

# Pod 故障排查标准流程

## 0. 确定 Pod 所在 Namespace（如未知）

```bash
# 根据 pod 名或部分名查找 namespace
kubectl get pods -A | grep <pod-name-pattern>
```

如果知道 pod 名但不确定 namespace，先执行以上命令定位。

## 1. 确认 Pod 状态

```bash
kubectl get pod <pod-name> -n <namespace> -o wide
kubectl describe pod <pod-name> -n <namespace>
```

重点关注：
- `STATUS` 列 (Running/Pending/CrashLoopBackOff)
- `RESTARTS` 次数
- `CONTAINER STATE` 和 `REASON`

## 2. 查看容器日志

```bash
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous  # 上一次运行日志
```

## 3. 常见状态与根因

| STATUS | 可能原因 |
|--------|---------|
| Pending | 资源不足、调度失败、PVC 未绑定 |
| ImagePullBackOff | 镜像不存在、认证失败 |
| CrashLoopBackOff | 应用崩溃、配置错误、probe 失败 |
| OOMKilled | 内存超过 limits |
| Unhealthy | liveness/readiness probe 持续失败 |

## 4. 查看 Events

```bash
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```
