---
id: E010
title: "Pod 网络不通"
category: network
description: "Pod 运行正常但无法与其他 Pod 或服务通信"
symptoms:
  - "Pod 无法访问其他 Pod IP"
  - "无法访问 ClusterIP Service"
  - "跨节点 Pod 不通"
  - "网络时通时断"
severity: critical
---

# Pod 网络不通

## 症状表现

- Pod 状态为 Running，但应用无法连接数据库/缓存
- 同一 Service 的后端 Pod 部分可访问，部分不可
- 跨节点 Pod 之间无法通信
- 网络间歇性中断

## 排查步骤

### 1. 检查 Pod IP 分配

```bash
# 查看 Pod 是否有 IP
kubectl get pod <pod-name> -o wide

# 检查 Pod 详情
describe pod <pod-name> | grep -A5 "IP:"
```

**预期结果**: Pod 应有分配的 IP 地址（如 10.244.x.x）

**关键判断**:
- Pod 启动 30 秒后仍无 IP → **CNI 插件问题**
- Pod 有 IP 但无法通信 → **网络策略或路由问题**

### 2. 检查 CNI 插件状态

```bash
# 查看 CNI 相关 Pod
kubectl get pods -n kube-system -l k8s-app=calico-node
kubectl get pods -n kube-system -l k8s-app=cilium
kubectl get pods -n kube-system -l app=flannel

# 查看 CNI Pod 日志
kubectl logs -n kube-system -l k8s-app=calico-node --tail=100
```

**预期结果**: CNI Pod 应全部 Running，日志无 ERROR

**常见问题**:
- CNI Pod 处于 CrashLoopBackOff → 检查 CNI 配置和 RBAC
- CNI Pod 处于 NotReady → 检查节点网络配置

### 3. 测试 Pod 连通性

```bash
# 进入源 Pod
kubectl exec -it <source-pod> -- sh

# 测试到目标 Pod 的连通
ping <target-pod-ip>
curl <target-pod-ip>:<port>

# 测试到 Service 的连通
nslookup <service-name>
curl <service-name>:<port>
```

**诊断矩阵**:

| 场景 | 可能原因 |
|------|----------|
| 同节点 Pod 通，跨节点不通 | CNI 路由/VXLAN 配置问题 |
| 能 ping 通 IP，但端口不通 | 目标应用未监听或防火墙 |
| 能通 Pod IP，不能通 Service IP | kube-proxy 问题 |
| 特定 Namespace 不通 | NetworkPolicy 阻断 |

### 4. 检查 NetworkPolicy

```bash
# 列出 Namespace 的所有 NetworkPolicy
kubectl get networkpolicy -n <namespace>

# 查看具体规则
kubectl describe networkpolicy <policy-name> -n <namespace>
```

**常见问题**:
- 默认拒绝所有入站流量 → 添加允许规则
- 标签选择器不匹配 → 修正 podSelector
- 未放行 DNS 端口 → 添加 53/UDP 规则

### 5. 检查 Service 和 Endpoints

```bash
# 检查 Service 配置
kubectl get svc <service-name> -o yaml

# 检查后端 Pod 是否正常注册
kubectl get endpoints <service-name>

# 检查 EndpointSlices（K8s 1.21+）
kubectl get endpointslices -l kubernetes.io/service-name=<service-name>
```

**预期结果**: Endpoints 应列出所有健康的后端 Pod IP

**常见问题**:
- Endpoints 为空 → Pod label 与 Service selector 不匹配
- Endpoints 缺少部分 Pod → 检查 Pod readinessProbe

### 6. 检查 kube-proxy

```bash
# 查看 kube-proxy Pod 状态
kubectl get pods -n kube-system -l k8s-app=kube-proxy

# 查看 kube-proxy 日志
kubectl logs -n kube-system -l k8s-app=kube-proxy --tail=100

# 检查 iptables/IPVS 规则（在节点上执行）
iptables -t nat -L KUBE-SERVICES -n | head
ipvsadm -Ln
```

**常见问题**:
- kube-proxy 模式不匹配（iptables vs IPVS）
- iptables 规则过多导致性能下降
- IPVS 配置错误

## CNI 专用诊断

### Calico

```bash
# 检查 Calico 节点状态
kubectl exec -n calico-system calico-node-xxx -- calico-node -status

# 检查 BGP 邻居
kubectl exec -n calico-system calico-node-xxx -- calicoctl node status

# 检查 IP Pool
calicoctl get ippool -o yaml
```

### Cilium

```bash
# 检查 Cilium 状态
cilium status

# 检查 Pod 连通性测试
cilium connectivity test

# 查看网络策略生效状态
kubectl exec -n kube-system cilium-xxx -- cilium endpoint list
```

### Flannel

```bash
# 检查 Flannel 子网分配
cat /run/flannel/subnet.env

# 检查 VTEP 设备
ip -d link show flannel.1

# 检查路由表
ip route | grep flannel
```

## 常见原因与解决方案

| 原因 | 症状 | 解决方案 |
|------|------|----------|
| CNI 插件未运行 | Pod 无 IP | 重启 CNI DaemonSet，检查 RBAC |
| CNI 配置错误 | CNI Pod CrashLoopBackOff | 修正 CNI ConfigMap |
| NetworkPolicy 阻断 | 特定流量不通 | 调整 NetworkPolicy 规则 |
| kube-proxy 异常 | Service IP 不通 | 重启 kube-proxy |
| 路由不可达 | 跨节点不通 | 检查 CNI 路由/VXLAN |
| MTU 不匹配 | 大包不通 | 统一集群 MTU 设置 |

## 诊断命令速查

```bash
# 一键网络诊断
kubectl run network-test --rm -it --image=nicolaka/netshoot --restart=Never -- bash

# 在诊断 Pod 内使用
ping <target-ip>
tracert <target-ip>
nmap -p <port> <target-ip>
tcpdump -i any host <target-ip>
```

## 参考链接

- [Kubernetes 网络故障排查指南](https://kubernetes.feisky.xyz/en/troubleshooting/network)
- [Troubleshooting CNI Plugin Errors](https://kubernetes.io/docs/tasks/administer-cluster/migrating-from-dockershim/troubleshooting-cni-plugin-related-errors/)
- [OneUptime - Kubernetes Networking Troubleshooting](https://oneuptime.com/blog/post/2026-01-19-kubernetes-troubleshoot-networking/view)
