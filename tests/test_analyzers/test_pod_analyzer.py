"""Test PodAnalyzer."""
from k8s_diagnose.analyzers.pod_analyzer import PodAnalyzer


class TestPodAnalyzer:
    def test_parse_pod_yaml(self):
        analyzer = PodAnalyzer()
        yaml_text = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
  namespace: default
spec:
  schedulerName: default
status:
  phase: Pending
"""
        data = analyzer.parse_pod_yaml(yaml_text)
        assert data["metadata"]["name"] == "test-pod"
        assert data["status"]["phase"] == "Pending"

    def test_parse_invalid_yaml(self):
        analyzer = PodAnalyzer()
        data = analyzer.parse_pod_yaml("not: valid: yaml: [")
        assert data == {}

    def test_get_pod_summary(self):
        analyzer = PodAnalyzer()
        pod_data = {
            "metadata": {"name": "my-pod", "namespace": "test"},
            "spec": {"schedulerName": "volcano"},
            "status": {"phase": "Running", "conditions": []},
        }
        summary = analyzer.get_pod_summary(pod_data)
        assert summary["name"] == "my-pod"
        assert summary["phase"] == "Running"
        assert summary["scheduler"] == "volcano"

    def test_container_waiting_imagepullbackoff(self):
        analyzer = PodAnalyzer()
        container_statuses = [
            {
                "name": "app",
                "state": {"waiting": {"reason": "ImagePullBackOff", "message": "unauthorized"}},
                "ready": False,
                "restartCount": 0,
            }
        ]
        results = analyzer.get_container_diagnostics(container_statuses)
        assert len(results) == 1
        assert results[0]["state"] == "Waiting"
        assert results[0]["reason"] == "ImagePullBackOff"
        assert "E001" in results[0]["matched_patterns"]

    def test_container_oomkilled(self):
        analyzer = PodAnalyzer()
        container_statuses = [
            {
                "name": "app",
                "state": {"terminated": {"reason": "OOMKilled", "exitCode": 137}},
                "ready": False,
                "restartCount": 3,
            }
        ]
        results = analyzer.get_container_diagnostics(container_statuses)
        assert results[0]["state"] == "Terminated"
        assert "E003" in results[0]["matched_patterns"]

    def test_analyze_full(self):
        analyzer = PodAnalyzer()
        yaml_text = """
apiVersion: v1
kind: Pod
metadata:
  name: test-pod
status:
  phase: Pending
  containerStatuses:
    - name: app
      state:
        waiting:
          reason: CrashLoopBackOff
          message: "back-off"
      ready: false
      restartCount: 5
"""
        result = analyzer.analyze({"yaml": yaml_text})
        assert result.pattern_id == "E002"
        assert "CrashLoopBackOff" in result.title
