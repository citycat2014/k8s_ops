"""Scheduler failure analyzer — analyzes FailedScheduling events."""
import re
from k8s_diagnose.analyzers.base import BaseAnalyzer, AnalysisResult
from k8s_diagnose.knowledge.error_patterns import ERROR_PATTERNS


class SchedulerAnalyzer(BaseAnalyzer):
    """Analyze FailedScheduling events to identify root cause."""

    # Common scheduling failure patterns in events
    INSUFFICIENT_CPU = re.compile(r"Insufficient\s+cpu", re.IGNORECASE)
    INSUFFICIENT_MEMORY = re.compile(r"Insufficient\s+memory", re.IGNORECASE)
    INSUFFICIENT_RESOURCE = re.compile(r"Insufficient\s+(\S+)", re.IGNORECASE)
    TAINT_UNTOLERATED = re.compile(r"untolerated\s+taint", re.IGNORECASE)
    NODE_SELECTOR = re.compile(r"node\s+(selector|affinity)", re.IGNORECASE)
    PVC_UNBOUND = re.compile(r"pod\s+has\s+unbound.*PersistentVolumeClaim", re.IGNORECASE)

    def analyze_scheduling_failure(
        self,
        events_text: str = "",
        nodes_text: str = "",
        pod_yaml: str = "",
    ) -> AnalysisResult:
        """Analyze scheduling failure from events + node info + pod spec."""
        pattern = ERROR_PATTERNS["E004"]  # FailedScheduling

        # Check events for known patterns
        if self.INSUFFICIENT_CPU.search(events_text):
            return AnalysisResult(
                pattern_id="E004",
                title="调度失败: CPU 资源不足",
                explanation="集群节点 CPU 不足，无法满足 Pod 的 CPU requests",
                confidence=0.85,
                suggested_actions=[
                    "扩容节点或降低 Pod CPU requests",
                    "清理不用的 Pod 释放资源",
                ],
            )

        if self.INSUFFICIENT_MEMORY.search(events_text):
            return AnalysisResult(
                pattern_id="E004",
                title="调度失败: 内存资源不足",
                explanation="集群节点内存不足，无法满足 Pod 的 memory requests",
                confidence=0.85,
                suggested_actions=[
                    "扩容节点或降低 Pod memory requests",
                    "清理不用的 Pod 释放资源",
                ],
            )

        if self.TAINT_UNTOLERATED.search(events_text):
            return AnalysisResult(
                pattern_id="E004",
                title="调度失败: 节点 Taint 阻止",
                explanation="目标节点有 Taint，但 Pod 没有对应的 Toleration",
                confidence=0.8,
                suggested_actions=[
                    "为 Pod 添加对应的 toleration",
                    "或移除节点的 taint",
                ],
            )

        if self.PVC_UNBOUND.search(events_text):
            return AnalysisResult(
                pattern_id="E004",
                title="调度失败: PVC 未绑定",
                explanation="Pod 依赖的 PVC 尚未绑定到 PV",
                confidence=0.75,
                suggested_actions=[
                    "检查 PVC 状态和 storageclass",
                    "确保 provisioner 可用",
                ],
            )

        # Generic fallback
        return AnalysisResult(
            pattern_id="E004",
            title="调度失败: 未知原因",
            explanation="FailedScheduling 事件存在，但未匹配到已知原因。请查看 events 详情",
            confidence=0.3,
            suggested_actions=["kubectl describe pod <name> -n <ns> 查看 events 详情"],
        )

    def analyze(self, data: dict) -> AnalysisResult:
        """Analyze from dict input (for BaseAnalyzer interface)."""
        return self.analyze_scheduling_failure(
            events_text=data.get("events", ""),
            nodes_text=data.get("nodes", ""),
            pod_yaml=data.get("pod_yaml", ""),
        )
