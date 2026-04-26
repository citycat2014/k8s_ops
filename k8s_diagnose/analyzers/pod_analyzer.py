"""Pod status analyzer — maps container states to diagnosis results."""
import yaml
from k8s_diagnose.analyzers.base import BaseAnalyzer, AnalysisResult
from k8s_diagnose.knowledge.error_patterns import ERROR_PATTERNS


class PodAnalyzer(BaseAnalyzer):
    """Analyze Pod YAML output from kubectl to extract diagnostics."""

    @staticmethod
    def parse_pod_yaml(yaml_text: str) -> dict:
        """Parse kubectl get pod -o yaml output into a dict."""
        try:
            data = yaml.safe_load(yaml_text)
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError:
            return {}

    @staticmethod
    def get_container_diagnostics(container_statuses: list) -> list[dict]:
        """Analyze each container's status and return diagnosis info."""
        results = []
        for cs in container_statuses or []:
            state_info = cs.get("state", {})
            ready = state_info.get("ready", False)
            reason = ""
            message = ""

            # Determine container state
            if "waiting" in state_info:
                state = "Waiting"
                reason = state_info["waiting"].get("reason", "")
                message = state_info["waiting"].get("message", "")
            elif "terminated" in state_info:
                state = "Terminated"
                reason = state_info["terminated"].get("reason", "")
                message = state_info["terminated"].get("message", "")
            elif "running" in state_info:
                state = "Running"
                reason = ""
                message = ""
            else:
                state = "Unknown"
                reason = ""
                message = ""

            # Check if this matches a known pattern
            match_text = f"{state} {reason} {message}"
            matched_patterns = [
                p for p in ERROR_PATTERNS.values()
                if p.matches(match_text)
            ]

            results.append({
                "name": cs.get("name", "unknown"),
                "state": state,
                "reason": reason,
                "message": message,
                "ready": ready,
                "restart_count": cs.get("restartCount", 0),
                "matched_patterns": [p.id for p in matched_patterns],
            })

        return results

    @staticmethod
    def get_pod_summary(pod_data: dict) -> dict:
        """Extract key Pod info for diagnosis."""
        status = pod_data.get("status", {})
        spec = pod_data.get("spec", {})

        return {
            "name": pod_data.get("metadata", {}).get("name", ""),
            "namespace": pod_data.get("metadata", {}).get("namespace", ""),
            "phase": status.get("phase", "Unknown"),
            "conditions": status.get("conditions", []),
            "scheduler": spec.get("schedulerName", "default"),
        }

    def analyze(self, data: dict) -> AnalysisResult:
        """Analyze raw kubectl output and return diagnosis."""
        yaml_text = data.get("yaml", "")
        events_text = data.get("events", "")

        if yaml_text:
            pod_data = self.parse_pod_yaml(yaml_text)
            summary = self.get_pod_summary(pod_data)
            container_statuses = pod_data.get("status", {}).get("containerStatuses", [])
            diagnostics = self.get_container_diagnostics(container_statuses)

            # Match patterns
            for d in diagnostics:
                if d["matched_patterns"]:
                    for pid in d["matched_patterns"]:
                        pattern = ERROR_PATTERNS.get(pid)
                        if pattern and pattern.possible_causes:
                            cause = pattern.possible_causes[0]
                            return AnalysisResult(
                                pattern_id=pid,
                                title=f"{pattern.name}: {cause.title}",
                                explanation=cause.explanation,
                                confidence=0.8,
                                suggested_actions=[cause.fix],
                            )

            return AnalysisResult(
                title=f"Pod {summary.get('name', 'unknown')} 状态: {summary.get('phase')}",
                explanation=str(diagnostics) if diagnostics else "无容器状态信息",
                confidence=0.3,
            )

        return AnalysisResult(
            title="无数据",
            explanation="未提供 Pod YAML 数据",
            confidence=0.0,
        )
