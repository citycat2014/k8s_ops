---
id: kb-faileddcheduling
title: FailedScheduling 排查指南
type: error-pattern
scope: pod/scheduling
complexity: intermediate
---

# FailedScheduling 排查

## 症状

Pod 状态为 Pending，Events 中显示 `FailedScheduling` 和 `nodes are available` 相关信息。

## 排查步骤

```bash
# 1. 查看 Pod 调度状态
kubectl describe pod <pod-name> -n <namespace>

# 2. 查看节点资源
kubectl top nodes

# 3. 查看节点 label
kubectl get nodes --show-labels

# 4. 查看节点 taint
kubectl describe node <node-name>
```

## 常见原因

1. **集群资源不足** — CPU/memory 耗尽，需扩容节点或降低 Pod requests
2. **NodeSelector/亲和性不匹配** — label 条件无节点满足
3. **Taint/Toleration 阻止** — 节点有 Taint 但 Pod 无对应 Toleration
4. **PVC 未绑定** — Pod 依赖的 PVC 状态为 Pending
