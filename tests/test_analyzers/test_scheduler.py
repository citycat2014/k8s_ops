"""Test SchedulerAnalyzer."""
from k8s_diagnose.analyzers.scheduler import SchedulerAnalyzer


class TestSchedulerAnalyzer:
    def test_insufficient_cpu(self):
        analyzer = SchedulerAnalyzer()
        events = "0/3 nodes are available: 3 Insufficient cpu."
        result = analyzer.analyze_scheduling_failure(events_text=events)
        assert result.pattern_id == "E004"
        assert "CPU" in result.title

    def test_insufficient_memory(self):
        analyzer = SchedulerAnalyzer()
        events = "0/5 nodes are available: 5 Insufficient memory."
        result = analyzer.analyze_scheduling_failure(events_text=events)
        assert result.pattern_id == "E004"
        assert "内存" in result.title

    def test_taint_untolerated(self):
        analyzer = SchedulerAnalyzer()
        events = "0/3 nodes: 3 node(s) had untolerated taint {dedicated=gpu:NoSchedule}."
        result = analyzer.analyze_scheduling_failure(events_text=events)
        assert result.pattern_id == "E004"
        assert "Taint" in result.title

    def test_pvc_unbound(self):
        analyzer = SchedulerAnalyzer()
        events = "pod has unbound PersistentVolumeClaim"
        result = analyzer.analyze_scheduling_failure(events_text=events)
        assert result.pattern_id == "E004"
        assert "PVC" in result.title

    def test_unknown_failure(self):
        analyzer = SchedulerAnalyzer()
        events = "some random event"
        result = analyzer.analyze_scheduling_failure(events_text=events)
        assert result.pattern_id == "E004"
        assert result.confidence == 0.3
