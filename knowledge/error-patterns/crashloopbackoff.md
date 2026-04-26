---
id: kb-crashloopbackoff
title: CrashLoopBackOff 排查指南
type: error-pattern
scope: pod/container
complexity: intermediate
---

# CrashLoopBackOff 排查

## 症状

Pod 状态为 Waiting，Reason 显示 `CrashLoopBackOff`，RESTARTS 持续增加。

## 排查步骤

```bash
# 1. 查看当前日志
kubectl logs <pod-name> -n <namespace>

# 2. 查看上一次崩溃的日志
kubectl logs <pod-name> -n <namespace> --previous

# 3. 查看容器退出码
kubectl describe pod <pod-name> -n <namespace>
```

## 常见原因

1. **应用启动失败** — 入口命令错误、配置文件缺失、依赖服务不可用
2. **ConfigMap/Secret 引用错误** — 挂载的配置不存在
3. **健康检查失败** — readiness/liveness probe 配置不当
