---
id: E015
title: "镜像拉取失败"
category: pod
description: "无法从镜像仓库拉取容器镜像"
symptoms:
  - "ImagePullBackOff"
  - "ErrImagePull"
  - "Back-off pulling image"
  - "认证失败"
severity: high
---

# 镜像拉取失败 (ImagePullBackOff)

## 症状表现

- Pod 状态: `ImagePullBackOff` 或 `ErrImagePull`
- `kubectl describe pod` 显示镜像拉取错误
- 事件中出现 `Failed to pull image`

## 排查步骤

### 1. 查看详细错误信息

```bash
kubectl describe pod <pod-name>
```

**关键 Events**:
```
Failed to pull image "nginx:1.99": rpc error: 
code = Unknown desc = Error response from daemon: 
manifest for nginx:1.99 not found
```

### 2. 检查镜像配置

```bash
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].image}'
```

**常见问题**:
- 镜像名称/标签错误
- 使用了不存在的版本
- 私有镜像未配置拉取密钥

### 3. 验证镜像存在性

```bash
# 本地测试拉取
docker pull <image-name>:<tag>

# 检查镜像标签是否存在
docker manifest inspect <image-name>:<tag>
```

### 4. 检查 ImagePullSecret

```bash
# 查看 Pod 配置的 secret
kubectl get pod <pod-name> -o jsonpath='{.spec.imagePullSecrets}'

# 检查 secret 内容
kubectl get secret <secret-name> -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d
```

## 常见原因与解决方案

### 原因 1: 镜像不存在或标签错误

**症状**: `manifest for xxx not found`

**解决方案**:
- 确认镜像名称拼写正确
- 确认镜像标签存在（可用 `latest` 测试）
- 检查镜像仓库地址

```bash
# 列出可用标签（Docker Hub）
curl -s https://registry.hub.docker.com/v2/repositories/library/nginx/tags/ | jq '.results[].name'
```

### 原因 2: 私有镜像无认证

**症状**: `unauthorized: authentication required`

**解决方案**:

1. 创建 Docker Registry Secret
```bash
kubectl create secret docker-registry regcred \
  --docker-server=<registry> \
  --docker-username=<username> \
  --docker-password=<password> \
  --docker-email=<email>
```

2. Pod 引用 Secret
```yaml
apiVersion: v1
kind: Pod
spec:
  imagePullSecrets:
  - name: regcred
  containers:
  - name: app
    image: private-registry/app:v1.0
```

3. 或配置 ServiceAccount 默认 Secret
```bash
kubectl patch serviceaccount default -p '{"imagePullSecrets": [{"name": "regcred"}]}'
```

### 原因 3: 网络不可达

**症状**: `dial tcp: i/o timeout` 或 `connection refused`

**排查**:
```bash
# 在节点上测试网络连通
telnet <registry-host> 443
nc -vz <registry-host> 443
```

**常见问题**:
- 防火墙阻断
- DNS 解析失败
- 需要代理
- 私有仓库无公网路由

**解决方案**:
- 配置 HTTP_PROXY/HTTPS_PROXY
- 使用内部镜像仓库/镜像代理
- 配置 registry mirror

### 原因 4: 镜像仓库速率限制

**症状**: `TOOMANYREQUESTS` 或 `rate limit exceeded`

**解决方案**:
- 使用镜像仓库的认证账户提升限额
- 配置镜像缓存（如 Harbor）
- 使用公有云镜像加速器

```bash
# 配置 Docker daemon 镜像加速
# /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.gcr.io",
    "https://registry.docker-cn.com"
  ]
}
```

### 原因 5: 节点磁盘空间不足

**症状**: `no space left on device`

**排查**:
```bash
df -h /var/lib/docker
docker system df
```

**解决方案**:
```bash
# 清理未使用镜像
docker image prune -a -f
# 或
docker system prune -a -f
```

### 原因 6: 镜像架构不匹配

**症状**: `exec format error` 或拉取成功但无法运行

**排查**:
```bash
# 检查镜像架构
docker manifest inspect <image> | grep architecture
```

**解决方案**: 使用多架构镜像或指定正确架构

## ImagePullBackOff 状态说明

Kubelet 镜像拉取失败后的重试策略:

| 失败次数 | 等待时间 |
|----------|----------|
| 1 | 10s |
| 2 | 20s |
| 3 | 40s |
| 4 | 80s |
| 5+ | 120s (max) |

状态切换: `Pending` → `ErrImagePull` → `ImagePullBackOff` → 重试

## 诊断命令速查

```bash
# 查看所有 ImagePullBackOff Pod
kubectl get pods --all-namespaces | grep ImagePullBackOff

# 快速诊断镜像问题
kubectl get pods --all-namespaces -o json | \
  jq '.items[] | select(.status.containerStatuses[]?.state.waiting?.reason == "ImagePullBackOff") | {name: .metadata.name, ns: .metadata.namespace, image: .spec.containers[0].image}'

# 查看节点镜像缓存
docker images | grep <image-name>
```

## 参考链接

- [Pull an Image from a Private Registry](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/)
- [Configure Service Accounts](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
