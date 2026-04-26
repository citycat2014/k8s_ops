"""Test error pattern matching."""
from k8s_diagnose.knowledge.error_patterns import ERROR_PATTERNS


class TestErrorPatterns:
    def test_all_patterns_have_id(self):
        for pid, pattern in ERROR_PATTERNS.items():
            assert pattern.id == pid
            assert len(pattern.name) > 0
            assert len(pattern.triggers) > 0

    def test_imagepullbackoff_matches(self):
        p = ERROR_PATTERNS["E001"]
        assert p.matches("Container image pull backoff ImagePullBackOff")
        assert p.matches("ErrImagePull error")
        assert not p.matches("Pod running healthy")

    def test_crashloopbackoff_matches(self):
        p = ERROR_PATTERNS["E002"]
        assert p.matches("Waiting CrashLoopBackOff")
        assert not p.matches("Running")

    def test_oomkilled_matches(self):
        p = ERROR_PATTERNS["E003"]
        assert p.matches("Terminated OOMKilled exitCode=137")
        assert not p.matches("Running")

    def test_failedscheduling_matches(self):
        p = ERROR_PATTERNS["E004"]
        assert p.matches("FailedScheduling 0/3 nodes available")
        assert p.matches("0/5 nodes are available: insufficient")

    def test_all_patterns_have_causes(self):
        for pid, pattern in ERROR_PATTERNS.items():
            assert len(pattern.possible_causes) > 0, f"{pid} has no causes"

    def test_cni_patterns_exist(self):
        assert "E006" in ERROR_PATTERNS
        assert "E007" in ERROR_PATTERNS
        assert ERROR_PATTERNS["E006"].matches("NetworkPluginNotReady")
        assert ERROR_PATTERNS["E007"].matches("NetworkPolicy blocked")

    def test_volcano_patterns_exist(self):
        assert "E008" in ERROR_PATTERNS
        p = ERROR_PATTERNS["E008"]
        assert p.matches("Gang Scheduling minAvailable not met")
        assert p.matches("0/5 tasks unschedulable")
