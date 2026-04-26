---
id: E009
title: "DNS 解析失败"
category: network
description: "Pod 内 DNS 解析异常，无法访问集群内部或外部域名"
symptoms:
  - "nslookup/dig 域名失败"
  - "连接外部服务超时"
  - "服务间调用失败"
  - "Pod 内 /etc/resolv.conf 配置异常"
severity: high
---

# DNS 解析失败

## 症状表现

- Pod 内执行 `nslookup kubernetes.default` 失败
- 访问集群内部 Service 域名超时
- 访问外部域名（如百度、Google）超时
- 报错 `Could not resolve host` 或 `Name or service not known`

## 排查步骤

### 1. 确认 DNS Pod 状态

```bash
# 查看 CoreDNS/DNS 相关 Pod
kubectl get pods -n kube-system -l k8s-app=kube-dns

# 检查 CoreDNS Pod 日志
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100
```

**预期结果**: CoreDNS Pod 应处于 Running 状态，日志无异常

**常见问题**:
- CoreDNS Pod 处于 CrashLoopBackOff → 检查配置 ConfigMap
- CoreDNS Pod 处于 Pending → 检查节点资源和调度

### 2. 检查 Pod 的 DNS 配置

```bash
# 进入问题 Pod
kubectl exec -it <pod-name> -- sh

# 查看 DNS 配置
cat /etc/resolv.conf
```

**预期结果**:
```
nameserver 10.96.0.10          # Cluster DNS IP
search <namespace>.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

**常见问题**:
- nameserver 指向错误 → 检查 kubelet 配置的 clusterDNS
- search 域缺失 → 检查 Pod dnsPolicy 配置

### 3. 测试 DNS 解析

```bash
# 在 Pod 内测试
nslookup kubernetes.default.svc.cluster.local
nslookup <service-name>.<namespace>.svc.cluster.local

# 测试外部 DNS
nslookup baidu.com
```

**预期结果**: 能正常返回 IP 地址

### 4. 检查 CoreDNS 配置

```bash
# 查看 CoreDNS ConfigMap
kubectl get configmap coredns -n kube-system -o yaml
```

**常见问题**:
- forward 配置错误 → 检查上游 DNS 服务器
- hosts 配置冲突 → 检查自定义 hosts 配置
- 循环引用 → CoreDNS 转发到自己导致循环

### 5. 检查网络连通性

```bash
# 测试到 CoreDNS 的网络连通
kubectl exec -it <pod-name> -- nc -zv 10.96.0.10 53

# 测试 UDP 53 端口
dig @10.96.0.10 kubernetes.default.svc.cluster.local
```

**常见问题**:
- 网络策略 (NetworkPolicy) 阻断 53/UDP → 检查 NetworkPolicy 规则
- CNI 问题导致无法访问 ClusterIP → 检查 CNI 插件状态

## 常见原因与解决方案

| 原因 | 症状 | 解决方案 |
|------|------|----------|
| CoreDNS Pod 异常 | CoreDNS 不在 Running 状态 | 重启或重建 CoreDNS Deployment |
| CoreDNS 配置错误 | 日志显示配置解析失败 | 修正 CoreDNS ConfigMap |
| 上游 DNS 不可达 | 外部域名解析失败 | 配置正确的 forward 上游 DNS |
| NetworkPolicy 阻断 | 特定 Namespace 的 Pod 无法解析 | 放行 53/UDP 流量 |
| kubelet 配置错误 | Pod /etc/resolv.conf 错误 | 修正 kubelet --cluster-dns 参数 |
| ndots 配置不当 | 外部域名解析慢或失败 | 调整 Pod dnsConfig ndots 值 |

## 诊断命令速查

```bash
# 快速诊断脚本
kubectl run -it --rm debug --image=busybox:1.28 --restart=Never -- sh

# 在 debug Pod 内执行
nslookup kubernetes.default
nslookup baidu.com
cat /etc/resolv.conf
```

## 参考链接

- [Kubernetes DNS 调试官方文档](https://kubernetes.io/docs/tasks/administer-cluster/dns-debugging-resolution/)
- [CoreDNS 故障排查](https://coredns.io/plugins/loop/)
