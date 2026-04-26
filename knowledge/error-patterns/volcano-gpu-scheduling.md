---
id: E019
title: "Volcano GPU 调度失败"
category: scheduling
description: "Volcano 调度器 GPU 相关调度失败，包括 Gang 死锁、GPU 配额、vGPU 内存等问题"
symptoms:
  - "PodGroup 状态 Pending"
  - "Gang 调度死锁"
  - "GPU 配额不足"
  - "vGPU 内存分配失败"
  - "GPU 碎片化导致调度失败"
severity: high
---

# Volcano GPU 调度失败

## 症状表现

- PodGroup 状态长时间处于 `Pending` 或 `Inqueue`
- Job/Pod 处于 `Pending`，describe 显示 gang unschedulable
- GPU 训练任务卡住，部分 Pod 运行，部分无法调度
- vGPU Pod 调度失败，报错资源不足
- 高优先级任务无法抢占 GPU 资源

## 排查步骤

### 1. 检查 PodGroup 状态

```bash
# 查看 PodGroup
kubectl get podgroup -n <namespace>

# 查看 PodGroup 详情
kubectl describe podgroup <pg-name> -n <namespace>
```

**关键字段**:
```yaml
status:
  phase: Pending  # Pending / Running / Unknown
  conditions:
  - type: Scheduled
    status: "False"
    reason: NotEnoughResources
    message: "1/2 tasks in gang unschedulable"
```

### 2. 查看 Volcano Job 状态

```bash
# 查看 VCJob
kubectl get vcjob -n <namespace>

# 查看 Job 详情
kubectl describe vcjob <job-name> -n <namespace>

# 查看 Pod 状态
kubectl get pods -l volcano.sh/job-name=<job-name> -n <namespace>
```

### 3. 检查调度器日志

```bash
# 查看 Volcano 调度器日志
kubectl logs -n volcano-system deploy/volcano-scheduler --tail=200

# 增加日志级别排查
# 修改 deployment 添加 --v=4 参数
```

**关键日志搜索**:
```bash
# Gang 调度失败
grep -i "gang" /var/log/volcano-scheduler.log

# GPU 资源不足
grep -i "gpu\|nvidia" /var/log/volcano-scheduler.log

# 预选失败原因
grep "fit failed\|predicate" /var/log/volcano-scheduler.log
```

### 4. 检查 GPU 节点资源

```bash
# 查看节点 GPU 资源
kubectl get nodes -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu,GPU-MEM:.status.allocatable.vgpu-memory,GPU-NUM:.status.allocatable.vgpu-number'

# 查看节点已分配 GPU
kubectl describe node <gpu-node> | grep -A20 "Allocated resources"

# 检查节点标签
kubectl get node <gpu-node> -o jsonpath='{.metadata.labels}' | jq . | grep -i gpu
```

**预期输出**:
```
Allocatable:
  nvidia.com/gpu:           8
  volcano.sh/vgpu-memory:   80000
  volcano.sh/vgpu-number:   10
Allocated:
  nvidia.com/gpu:           6
  volcano.sh/vgpu-memory:   60000
```

### 5. 检查 vGPU 配置

```bash
# 查看 vGPU device plugin
kubectl get pods -n kube-system -l app.kubernetes.io/name=volcano-vgpu-device-plugin

# 查看 vGPU ConfigMap
kubectl get configmap volcano-vgpu-device-plugin -n kube-system -o yaml

# 查看节点 vGPU 分配
kubectl get node <node> -o jsonpath='{.status.allocatable}' | jq . | grep vgpu
```

## 常见原因与解决方案

### 原因 1: Gang 调度死锁

**症状**: PodGroup 部分 Pod 运行，部分 Pending，状态显示 `1/N tasks in gang unschedulable`

**场景**: 
- 分布式训练需要 N 个 Pod 同时启动
- 集群资源只能满足部分 Pod
- Gang 调度要求全有或全无

**排查**:
```bash
# 查看 PodGroup 的 minMember
kubectl get podgroup <pg-name> -o jsonpath='{.spec.minMember}'

# 查看实际运行的 Pod 数
kubectl get pods -l volcano.sh/job-name=<job-name> --field-selector=status.phase=Running | wc -l
```

**解决方案**:

1. **增加资源** - 扩容 GPU 节点

2. **调整 minMember**（谨慎使用）
```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: PodGroup
spec:
  minMember: 2  # 从 N 降低到可运行的数量
```

3. **使用 Job 级 Gang 而非 Task 级**
```yaml
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
spec:
  policies:
  - action: CompleteJob
    event: PodEvicted
  - action: CompleteJob  # 任一 Task 完成即结束
    event: PodFailed
```

4. **配置 Queue 优先级**
```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
metadata:
  name: gpu-training
spec:
  weight: 10  # 权重越高优先级越高
  capability:
    cpu: 100
    memory: 1000Gi
    nvidia.com/gpu: 16
```

### 原因 2: GPU 配额不足

**症状**: 调度器日志显示 GPU quota exceeded

**排查**:
```bash
# 查看 Queue 配额
kubectl get queue <queue-name> -o yaml

# 查看已使用配额
kubectl get queue <queue-name> -o jsonpath='{.status.running}'
```

**解决方案**:

1. **增加 Queue Capability**
```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
spec:
  capability:
    nvidia.com/gpu: 32  # 增加 GPU 配额
```

2. **检查 Namespace ResourceQuota**
```bash
kubectl get resourcequota -n <namespace>
kubectl describe resourcequota <quota-name> -n <namespace>
```

3. **调整 Job 的 GPU 请求**
```yaml
spec:
  tasks:
  - replicas: 4
    template:
      spec:
        containers:
        - resources:
            limits:
              nvidia.com/gpu: 1  # 从 2 降低到 1
```

### 原因 3: vGPU 内存不足

**症状**: `Insufficient volcano.sh/vgpu-memory`

**场景**:
- 使用 `volcano.sh/vgpu-memory` 而非物理 GPU
- 多容器 Pod 中 vGPU 内存设置问题

**排查**:
```bash
# 查看节点可用 vGPU 内存
kubectl get node <node> -o jsonpath='{.status.allocatable.vgpu-memory}'

# 查看已分配 vGPU 内存
kubectl describe node <node> | grep vgpu-memory
```

**解决方案**:

1. **正确配置 vGPU 内存**
```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: training
    resources:
      limits:
        volcano.sh/vgpu-memory: 3000  # 3GB GPU 内存
        volcano.sh/vgpu-number: 1     # 1 个 vGPU
```

2. **多容器配置注意事项**（Issue #1858）
```yaml
# 避免在同一个 Pod 内为多个容器设置 vgpu-memory
# 建议：每个 Pod 只给主容器分配 vGPU
spec:
  containers:
  - name: main
    resources:
      limits:
        volcano.sh/vgpu-memory: 3000
  - name: sidecar
    # 不设置 vGPU，或设置 vgpu-number: 0
```

3. **调整 GPU 内存因子**
```bash
# 在 volcano-scheduler 配置中设置
# --gpu-memory-factor=10
# 表示 vGPU 内存按 10 的倍数分配
```

### 原因 4: GPU 碎片化

**症状**: 节点显示有 GPU 空闲，但无法调度需要多卡的 Pod

**场景**:
- 4 GPU 节点，已有 2 个 Pod 各占 1 GPU
- 需要 2 GPU 的 Pod 无法调度（虽然剩余 2 GPU）
- 分布在不同 PCIe Switch 或 NUMA 节点

**排查**:
```bash
# 查看节点 GPU 拓扑
nvidia-smi topo -m

# 查看 GPU 分配情况
kubectl get pods --all-namespaces -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,GPU:.spec.containers[*].resources.limits.nvidia\.com/gpu' | grep <node>
```

**解决方案**:

1. **配置 GPU 拓扑感知调度**
```yaml
# volcano-scheduler.conf
actions: "enqueue, allocate, backfill"
tiers:
- plugins:
  - name: priority
  - name: gang
  - name: conformance
- plugins:
  - name: drf
  - name: predicates
  - name: nodeorder
  - name: binpack
  - name: topology  # 启用拓扑感知
```

2. **使用 Binpack 插件减少碎片化**
```yaml
# 启用 Binpack 让 GPU 集中使用
tiers:
- plugins:
  - name: binpack
    arguments:
      binpack.weight: 10
      binpack.cpu: 1
      binpack.memory: 1
      nvidia.com/gpu: 10  # GPU 权重最高
```

3. **手动清理碎片**
```bash
# 迁移小 GPU 作业，腾出连续 GPU
# 或使用 Pod 驱逐重新调度
kubectl delete pod <small-gpu-pod> --grace-period=0
```

### 原因 5: 优先级抢占失败

**症状**: 高优先级任务无法抢占低优先级任务的 GPU

**场景**（Issue #3186）:
- vGPU 模式下不支持抢占
- 低优先级任务占用了物理 GPU

**排查**:
```bash
# 查看 Pod 优先级
kubectl get pods -o custom-columns='NAME:.metadata.name,PRIORITY:.spec.priority,CLASS:.spec.priorityClassName'

# 查看优先级定义
kubectl get priorityclass
```

**解决方案**:

1. **使用物理 GPU 模式（支持抢占）**
```yaml
spec:
  tasks:
  - template:
      spec:
        containers:
        - resources:
            limits:
              nvidia.com/gpu: 2  # 物理 GPU 支持抢占
```

2. **配置优先级和抢占**
```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
spec:
  reclaimable: true  # 允许回收
  weight: 10
```

3. **使用 Reservation 预留资源**
```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: Reservation
metadata:
  name: gpu-reservation
spec:
  owners:
  - name: high-priority-job
  resources:
    nvidia.com/gpu: 4
```

### 原因 6: 调度器配置错误

**症状**: 所有 GPU 调度失败，日志显示插件未启用

**排查**:
```bash
# 查看调度器配置
kubectl get configmap volcano-scheduler-configmap -n volcano-system -o yaml
```

**解决方案**:

1. **确保 GPU 相关插件启用**
```yaml
# volcano-scheduler.conf
tiers:
- plugins:
  - name: priority
  - name: gang
  - name: conformance
- plugins:
  - name: drf
  - name: predicates
    arguments:
      predicate.GPUSharingEnable: true  # 启用 GPU 共享
  - name: nodeorder
  - name: proportion
  - name: binpack
  - name: device-share  # 设备共享插件
```

2. **重启调度器**
```bash
kubectl rollout restart deploy/volcano-scheduler -n volcano-system
```

## Volcano GPU 配置最佳实践

### 物理 GPU Job

```yaml
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: gpu-job
spec:
  schedulerName: volcano
  queue: default
  tasks:
  - replicas: 4
    name: worker
    template:
      spec:
        containers:
        - name: training
          image: nvidia/cuda:11.8.0-runtime-ubuntu22.04
          command: ["python", "train.py"]
          resources:
            limits:
              nvidia.com/gpu: 2  # 每个 Pod 2 GPU
            requests:
              nvidia.com/gpu: 2
```

### vGPU Job

```yaml
apiVersion: batch.volcano.sh/v1alpha1
kind: Job
metadata:
  name: vgpu-job
spec:
  schedulerName: volcano
  tasks:
  - replicas: 2
    name: worker
    template:
      spec:
        containers:
        - name: training
          image: nvidia/cuda:11.8.0-runtime-ubuntu22.04
          resources:
            limits:
              volcano.sh/vgpu-memory: 4000  # 4GB 显存
              volcano.sh/vgpu-number: 1     # 1 个 vGPU
```

### 多租户队列配置

```yaml
apiVersion: scheduling.volcano.sh/v1beta1
kind: Queue
metadata:
  name: team-gpu
spec:
  weight: 5
  capability:
    cpu: 100
    memory: 400Gi
    nvidia.com/gpu: 16
  reclaimable: true  # 允许高优先级抢占
---
apiVersion: scheduling.volcano.sh/v1beta1
kind: PodGroup
metadata:
  name: gang-training
spec:
  minMember: 4
  queue: team-gpu
  priorityClassName: high-priority
```

## 诊断命令速查

```bash
# 查看所有 GPU 相关 PodGroup
kubectl get podgroups --all-namespaces -o custom-columns='NAME:.metadata.name,PHASE:.status.phase,MIN:.spec.minMember,RUNNING:.status.running'

# 查看 Queue 状态
kubectl get queues -o custom-columns='NAME:.metadata.name,STATE:.spec.state,CAP:.spec.capability,WEIGHT:.spec.weight'

# 查看节点 GPU 分配详情
kubectl get nodes -o json | jq '.items[] | {name: .metadata.name, labels: .metadata.labels, allocatable: .status.allocatable}' | grep -A10 "nvidia"

# 快速诊断 Gang 调度
kubectl get podgroups --all-namespaces | grep -v Running | grep -v Completed

# 查看 vGPU 插件状态
kubectl get pods -n kube-system -l component=volcano-vgpu-device-plugin
```

## 监控告警

```yaml
# Prometheus 告警规则
- alert: VolcanoGPUJobPending
  expr: volcano_queue_job_inqueue > 0
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Volcano GPU Job pending in queue"
    
- alert: VolcanoPodGroupGangFailed
  expr: volcano_podgroup_status_phase{phase="Pending"} > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "PodGroup Gang scheduling failed"
```

## 参考链接

- [Volcano PodGroup Issue #3910](https://github.com/volcano-sh/volcano/issues/3910) - PodGroup stuck in Pending
- [Volcano GPU Quota Issue #3426](https://github.com/volcano-sh/volcano/issues/3426) - GPU quota scheduling failed
- [NVIDIA GPU Fragmentation Prevention](https://developer.nvidia.cn/blog/practical-tips-for-preventing-gpu-fragmentation-for-volcano-scheduler/)
- [Volcano vGPU User Guide](https://volcano.sh/en/docs/user-guide/how_to_use_volcano_vgpu/)
- [Volcano GPU Virtualization](https://volcano.sh/en/docs/v1-11-0/gpu_virtualization/)
- [Volcano vGPU Memory Issue #1858](https://github.com/volcano-sh/volcano/issues/1858)
- [Volcano vGPU Preemption Issue #3186](https://github.com/volcano-sh/volcano/issues/3186)
- [Gang Scheduling Deadlock Analysis](https://blog.csdn.net/weixin_29227425/article/details/158711436)
