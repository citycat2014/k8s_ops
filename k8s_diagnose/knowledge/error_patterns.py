"""Known error pattern database for K8s diagnosis.

Each pattern includes: triggers, possible causes, verification commands, and fixes.
"""
from dataclasses import dataclass, field


@dataclass
class Cause:
    """A possible cause with verification and fix instructions."""
    title: str
    explanation: str
    evidence_check: str
    fix: str


@dataclass
class ErrorPattern:
    """A known K8s error pattern."""
    id: str
    name: str
    container_state: str | None
    triggers: list[str]
    possible_causes: list[Cause] = field(default_factory=list)

    def matches(self, text: str) -> bool:
        """Check if the pattern matches given text."""
        return any(t in text for t in self.triggers)


ERROR_PATTERNS: dict[str, ErrorPattern] = {
    "E001": ErrorPattern(
        id="E001",
        name="ImagePullBackOff",
        container_state="Waiting",
        triggers=["ImagePullBackOff", "ErrImagePull"],
        possible_causes=[
            Cause(
                "镜像不存在",
                "镜像名/tag 拼写错误或已被删除",
                "kubectl 本地尝试 docker pull",
                "修正 image 名称和 tag",
            ),
            Cause(
                "镜像仓库认证失败",
                "缺少 imagePullSecrets 或凭证过期",
                "检查 Pod spec.imagePullSecrets + Secret 内容",
                "创建/更新 imagePullSecret 并绑定到 ServiceAccount",
            ),
            Cause(
                "注册表不可达",
                "网络问题或 DNS 解析失败",
                "从节点 ping 注册表域名",
                "检查节点网络 + DNS 配置",
            ),
        ],
    ),
    "E002": ErrorPattern(
        id="E002",
        name="CrashLoopBackOff",
        container_state="Waiting",
        triggers=["CrashLoopBackOff"],
        possible_causes=[
            Cause(
                "应用启动失败",
                "入口命令错误、配置文件缺失、依赖服务不可用",
                "查看当前/上次日志",
                "修复应用配置或代码",
            ),
            Cause(
                "ConfigMap/Secret 引用错误",
                "挂载的 ConfigMap/Secret 不存在",
                "检查 events 中是否有 CreateContainerConfigError",
                "创建缺失的配置资源或修正引用",
            ),
            Cause(
                "健康检查失败导致重启",
                "readiness/liveness probe 持续失败",
                "查看 probe 配置和容器端口",
                "修正 probe 路径/端口/阈值",
            ),
        ],
    ),
    "E003": ErrorPattern(
        id="E003",
        name="OOMKilled",
        container_state="Terminated",
        triggers=["OOMKilled"],
        possible_causes=[
            Cause(
                "内存超限制",
                "容器实际使用内存超过 resources.limits.memory",
                "对比 usage 和 limit",
                "提高 memory limit 或优化应用内存使用",
            ),
        ],
    ),
    "E004": ErrorPattern(
        id="E004",
        name="FailedScheduling",
        container_state=None,
        triggers=["FailedScheduling", "nodes are available"],
        possible_causes=[
            Cause(
                "集群资源不足",
                "所有节点 CPU/memory 不足",
                "检查 node Allocatable vs Pod requests",
                "扩容节点或降低 Pod 资源请求",
            ),
            Cause(
                "NodeSelector/亲和性不匹配",
                "label/taint 条件无节点满足",
                "对比 Pod spec.nodeSelector 和 node labels",
                "调整调度约束或给节点打 label",
            ),
            Cause(
                "Taint/Toleration 阻止",
                "节点有 Taint 但 Pod 没有对应 Toleration",
                "检查 node.taints + pod.tolerations",
                "添加 toleration 或移除 taint",
            ),
            Cause(
                "PVC 未绑定",
                "Pod 依赖的 PVC 状态为 Pending",
                "检查 PVC 的 storageclass 和 provisioner",
                "创建 PV 或修正 storageclass",
            ),
        ],
    ),
    "E005": ErrorPattern(
        id="E005",
        name="Unhealthy",
        container_state="Running",
        triggers=["Unhealthy", "Liveness probe failed", "Readiness probe failed"],
        possible_causes=[
            Cause(
                "Liveness probe 失败导致重启",
                "应用响应慢或 probe 路径配置错误",
                "检查 probe path/port + 应用日志",
                "修正 probe 配置或修复应用启动延迟",
            ),
            Cause(
                "Readiness probe 导致摘流量",
                "就绪检查未通过，Service 不转发",
                "检查 readiness probe + 后端端口",
                "调整 initialDelaySeconds 或修复 readiness endpoint",
            ),
        ],
    ),
    "E006": ErrorPattern(
        id="E006",
        name="CNI插件异常",
        container_state=None,
        triggers=["NetworkPluginNotReady", "cni config uninitialized"],
        possible_causes=[
            Cause(
                "CNI 插件未就绪",
                "CNI 插件 Pod 未 Running 或配置缺失",
                "kubectl get pods -n kube-system -l k8s-app=calico-node/cilium/flannel",
                "修复 CNI 插件或等待插件就绪",
            ),
            Cause(
                "IP 池耗尽",
                "Calico IPAM 无可用 IP",
                "检查 IPAM 配置和已分配 IP 数",
                "扩大 IP 池或释放未用 IP",
            ),
        ],
    ),
    "E007": ErrorPattern(
        id="E007",
        name="Pod网络不通",
        container_state="Running",
        triggers=["NetworkPolicy", "connection refused", "connection timed out"],
        possible_causes=[
            Cause(
                "NetworkPolicy 阻断",
                "NetworkPolicy 规则未放行目标端口",
                "kubectl get networkpolicy -n <ns>",
                "修正 NetworkPolicy 规则",
            ),
            Cause(
                "DNS 解析失败",
                "CoreDNS 异常或 Pod resolv.conf 配置错误",
                "检查 CoreDNS 日志 + Pod /etc/resolv.conf",
                "修复 CoreDNS 或修正 DNS 配置",
            ),
        ],
    ),
    "E008": ErrorPattern(
        id="E008",
        name="Volcano Gang Scheduling 死锁",
        container_state=None,
        triggers=["Gang Scheduling", "minAvailable", "unschedulable"],
        possible_causes=[
            Cause(
                "集群资源不足以支持 Gang 调度",
                "集群总资源无法满足 PodGroup minAvailable",
                "对比 PodGroup minAvailable vs 节点可用资源",
                "扩容节点或降低 minAvailable",
            ),
            Cause(
                "Queue 资源配额不足",
                "Queue 已耗尽 deserved 资源",
                "kubectl get queue -o yaml",
                "调整 Queue 配额或释放其他队列资源",
            ),
            Cause(
                "调度器配置错误",
                "Pod schedulerName 未指定为 volcano",
                "检查 Pod spec.schedulerName",
                "设置 spec.schedulerName: volcano",
            ),
        ],
    ),
}
