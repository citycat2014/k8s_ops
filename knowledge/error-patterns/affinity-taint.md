---
id: E017
title: "调度失败 - 亲和性/污点"
category: scheduling
description: "NodeSelector、NodeAffinity、Taint/Toleration 导致无法调度"
symptoms:
  - "0/X nodes are available: didn't match node selector"
  - "0/X nodes are available: didn't match Pod's node affinity"
  - "0/X nodes are available: had taint"
severity: medium
---

# 调度失败 - 亲和性/污点

## 症状表现

- Pod 状态 `Pending`
- 调度失败事件显示亲和性/选择器不匹配
- 节点存在但无法调度

## 排查步骤

### 1. 查看调度失败原因

```bash
kubectl describe pod <pod-name> | grep -A10 "FailedScheduling"
```

**典型错误**:
```
0/3 nodes are available: 
1 node(s) didn't match Pod's node affinity/selector, 
2 node(s) had taint {node-role.kubernetes.io/control-plane: }, 
that the pod didn't tolerate.
```

### 2. 检查 Pod 亲和性配置

```bash
# NodeSelector
kubectl get pod <pod-name> -o jsonpath='{.spec.nodeSelector}'

# NodeAffinity
kubectl get pod <pod-name> -o jsonpath='{.spec.affinity.nodeAffinity}'

# Tolerations
kubectl get pod <pod-name> -o jsonpath='{.spec.tolerations}'
```

### 3. 检查节点标签

```bash
# 查看所有节点标签
kubectl get nodes --show-labels

# 查看特定节点
kubectl get node <node-name> -o jsonpath='{.metadata.labels}' | jq .
```

### 4. 检查节点污点

```bash
# 查看所有节点污点
kubectl get nodes -o json | \
  jq '.items[] | {name: .metadata.name, taints: .spec.taints}'

# 查看特定节点
kubectl describe node <node-name> | grep -A10 "Taints"
```

## 常见原因与解决方案

### 原因 1: NodeSelector 不匹配

**症状**: `didn't match node selector`

**排查**:
```bash
# Pod 要求
kubectl get pod <pod-name> -o jsonpath='{.spec.nodeSelector}'
# 输出: {"disktype": "ssd"}

# 节点实际标签
kubectl get node <node-name> -o jsonpath='{.metadata.labels.disktype}'
# 输出: (空或不同值)
```

**解决方案**:

1. 给节点添加标签
```bash
kubectl label nodes <node-name> disktype=ssd
```

2. 或修改 Pod 的 nodeSelector

### 原因 2: NodeAffinity 规则不满足

**症状**: `didn't match Pod's node affinity`

**示例配置**:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: topology.kubernetes.io/zone
          operator: In
          values:
          - us-east-1a
          - us-east-1b
```

**排查**:
```bash
# 检查节点是否有对应标签
kubectl get nodes -l topology.kubernetes.io/zone=us-east-1a
```

**解决方案**: 添加 toleration 或修改亲和性规则

### 原因 3: 节点污点未容忍

**症状**: `had taint {key: value}, that the pod didn't tolerate`

**常见污点**:
- `node-role.kubernetes.io/control-plane:NoSchedule` - 控制平面节点
- `node.kubernetes.io/not-ready:NoSchedule` - 节点未就绪
- `dedicated=production:NoSchedule` - 专用节点

**解决方案**:

```yaml
tolerations:
# 容忍控制平面污点
- key: "node-role.kubernetes.io/control-plane"
  operator: "Exists"
  effect: "NoSchedule"

# 容忍专用节点
- key: "dedicated"
  operator: "Equal"
  value: "production"
  effect: "NoSchedule"

# 容忍所有污点（不推荐生产使用）
- operator: "Exists"
```

### 原因 4: PodAntiAffinity 冲突

**症状**: 新 Pod 无法调度到已有同类 Pod 的节点

**排查**:
```yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
    - labelSelector:
        matchLabels:
          app: web
      topologyKey: kubernetes.io/hostname
```

**说明**: 同一节点上不能运行两个 `app=web` 的 Pod

### 原因 5: 拓扑分布约束

**症状**: `violated TopologySpreadConstraint`

```yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: DoNotSchedule
  labelSelector:
    matchLabels:
      app: web
```

## 调度约束对比

| 机制 | 用途 | 强制/偏好 |
|------|------|----------|
| nodeSelector | 简单节点选择 | 强制 |
| NodeAffinity required | 复杂节点选择 | 强制 |
| NodeAffinity preferred | 复杂节点选择 | 偏好 |
| Taint/Toleration | 节点排斥 | 强制（对不容忍的 Pod）|
| PodAffinity | Pod 吸引 | 强制/偏好 |
| PodAntiAffinity | Pod 排斥 | 强制/偏好 |

## 诊断命令速查

```bash
# 查找有特定标签的节点
kubectl get nodes -l <key>=<value>

# 查找有特定污点的节点
kubectl get nodes -o json | jq '.items[] | select(.spec.taints[]?.key == "<taint-key>") | .metadata.name'

# 快速调度诊断
kubectl get pod <pod-name> -o json | jq '.spec | {nodeSelector, affinity, tolerations}'
```

## 参考链接

- [Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
