---
id: kb-imagepullbackoff
title: ImagePullBackOff 排查指南
type: error-pattern
scope: pod/container
complexity: beginner
---

# ImagePullBackOff 排查

## 症状

Pod 状态为 Waiting，Reason 显示 `ImagePullBackOff` 或 `ErrImagePull`。

## 排查步骤

```bash
# 1. 查看 Pod 详情确认镜像名
kubectl describe pod <pod-name> -n <namespace>

# 2. 检查 imagePullSecrets
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.imagePullSecrets}'

# 3. 验证 Secret 内容
kubectl get secret <secret-name> -n <namespace> -o yaml
```

## 常见原因

1. **镜像名称或 tag 错误** — 修正 image 字段
2. **缺少 imagePullSecrets** — 创建 Secret 并绑定到 ServiceAccount
3. **镜像仓库不可达** — 检查节点网络 + DNS
