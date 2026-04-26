---
id: kb-kubectl-command-guide
title: kubectl 命令行使用指南
type: command-guide
scope: general
complexity: beginner
---

# kubectl 命令行使用指南

## 根据 Pod 名查找 Namespace

```bash
# 根据 pod 名称（或部分名称）在所有 namespace 中查找
kubectl get pods -A | grep <pod-pattern>

# 示例：查找包含 "web-app" 的 pod
kubectl get pods -A | grep web-app

# 查看找到的 pod 详情
kubectl get pod <pod-name> -n <namespace> -o yaml
```

## 查看 Pod

```bash
# 获取 Pod 简要信息
kubectl get pods -n <namespace>

# 获取 Pod 完整 YAML
kubectl get pod <pod-name> -n <namespace> -o yaml

# 获取 Pod 详细描述
kubectl describe pod <pod-name> -n <namespace>

# 列出所有 Pod（包含节点信息）
kubectl get pods -n <namespace> -o wide
```

## 查看日志

```bash
# 查看容器日志
kubectl logs <pod-name> -n <namespace>

# 查看上一次运行的日志（崩溃排查）
kubectl logs <pod-name> -n <namespace> --previous

# 实时跟踪日志
kubectl logs -f <pod-name> -n <namespace>

# 多容器 Pod 指定容器
kubectl logs <pod-name> -c <container-name> -n <namespace>
```

## 查看节点

```bash
# 节点列表
kubectl get nodes -o wide

# 节点详情
kubectl describe node <node-name>

# 节点资源使用
kubectl top node
```

## 查看 Events

```bash
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```
