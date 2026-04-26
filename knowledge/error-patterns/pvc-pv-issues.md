---
id: E018
title: "持久卷问题"
category: storage
description: "PVC 无法绑定、PV 挂载失败或存储相关错误"
symptoms:
  - "Pending PVC"
  - "FailedMount"
  - "Volume node affinity conflict"
  - "Unable to attach or mount volumes"
severity: high
---

# 持久卷问题

## 症状表现

- PVC 状态 `Pending`
- Pod 事件 `FailedMount`
- `Volume node affinity conflict`
- 无法挂载存储卷

## 排查步骤

### 1. 查看 PVC 状态

```bash
kubectl get pvc -n <namespace>

kubectl describe pvc <pvc-name>
```

### 2. 查看 Pod 挂载事件

```bash
kubectl describe pod <pod-name> | grep -A5 "FailedMount\|MountVolume"
```

### 3. 检查 PV 状态

```bash
kubectl get pv
kubectl describe pv <pv-name>
```

## 常见原因与解决方案

### 原因 1: PVC 无可用 PV

**症状**: PVC 一直处于 Pending，无 PV 绑定

**排查**:
```bash
# 检查 StorageClass
kubectl get storageclass

# 检查默认 SC
kubectl get storageclass -o json | jq '.items[] | select(.metadata.annotations."storageclass.kubernetes.io/is-default-class" == "true") | .metadata.name'
```

**解决方案**:

1. 启用动态供应
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard
provisioner: kubernetes.io/gce-pd  # 根据环境调整
parameters:
  type: pd-standard
```

2. 手动创建 PV
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: manual-pv
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /data/pv
```

### 原因 2: Volume Node Affinity Conflict

**症状**: Pod 调度到节点 A，但 PV 只能在节点 B 访问

**排查**:
```bash
# 查看 PV 的节点亲和性
kubectl get pv <pv-name> -o jsonpath='{.spec.nodeAffinity}'
```

**示例输出**:
```yaml
nodeAffinity:
  required:
    nodeSelectorTerms:
    - matchExpressions:
      - key: topology.kubernetes.io/zone
        operator: In
        values:
        - us-east-1a
```

**解决方案**:
- 使用支持多节点访问的存储（如 NFS、Ceph RBD）
- 或确保 Pod 调度到 PV 所在区域

### 原因 3: 挂载点被占用

**症状**: `Unable to mount volumes for pod: device is busy`

**解决方案**:
```bash
# 在节点上强制卸载
umount -f /var/lib/kubelet/pods/<pod-uid>/volumes/...

# 重启 kubelet
systemctl restart kubelet
```

### 原因 4: 存储类配置错误

**症状**: 动态供应失败

**排查**:
```bash
# 查看 provisioner 日志
kubectl logs -n kube-system -l app=csi-driver
```

**常见问题**:
- 云厂商认证失败
- CSI 插件未正确部署
- 配额不足

### 原因 5: 权限问题

**症状**: `Permission denied` 挂载后无法读写

**解决方案**:
```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    volumeMounts:
    - name: data
      mountPath: /data
    securityContext:
      runAsUser: 1000
      fsGroup: 1000  # 设置卷所有权
  volumes:
  - name: data
    persistentVolumeClaim:
      claimName: mypvc
```

### 原因 6: PVC 扩容失败

**症状**: 修改 PVC size 后无法生效

**排查**:
```bash
# 检查 StorageClass 是否允许扩容
kubectl get storageclass <sc-name> -o jsonpath='{.allowVolumeExpansion}'
```

**解决方案**:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: expandable
allowVolumeExpansion: true  # 启用扩容
```

## 访问模式说明

| 访问模式 | 缩写 | 说明 |
|----------|------|------|
| ReadWriteOnce | RWO | 单节点读写 |
| ReadOnlyMany | ROX | 多节点只读 |
| ReadWriteMany | RWX | 多节点读写 |
| ReadWriteOncePod | RWOP | 单 Pod 读写 (1.22+) |

## 存储类型选择

| 存储类型 | 访问模式 | 适用场景 |
|----------|----------|----------|
| hostPath | RWO | 单节点测试 |
| local | RWO | 本地 SSD 高性能 |
| NFS | RWX | 共享存储 |
| EBS/GCE PD | RWO | 云盘 |
| Ceph RBD | RWO | 分布式块存储 |
| CephFS | RWX | 分布式文件存储 |

## 诊断命令速查

```bash
# 查看所有 Pending PVC
kubectl get pvc --all-namespaces | grep Pending

# 查看 PV/PVC 绑定关系
kubectl get pv -o custom-columns='NAME:.metadata.name,CLAIM:.spec.claimRef.name,STATUS:.status.phase'

# 节点挂载点检查
find /var/lib/kubelet/pods -name "mounts" 2>/dev/null | head
```

## 参考链接

- [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Storage Classes](https://kubernetes.io/docs/concepts/storage/storage-classes/)
