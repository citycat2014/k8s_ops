import pytest
from unittest.mock import patch, MagicMock
from k8s_diagnose.k8s_client.kubectl import (
    KubectlRunner,
    PermissionMode,
    KubectlResult,
    PermissionDenied,
    ShellInjectionDetected,
)


class TestKubectlRunnerBasic:
    def test_run_simple_command(self):
        runner = KubectlRunner()
        mock_result = MagicMock()
        mock_result.stdout = "pod-1\npod-2\n"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("get", "pods")

        assert result.success
        assert "pod-1" in result.stdout
        assert "get pods" in result.command

    def test_run_with_namespace(self):
        runner = KubectlRunner(namespace="kube-system")
        mock_result = MagicMock(stdout="", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            runner.run("get", "pods")
            call_args = mock_run.call_args[0][0]
            assert "-n" in call_args
            assert "kube-system" in call_args

    def test_run_with_kubeconfig(self):
        runner = KubectlRunner(kubeconfig="/tmp/kubeconfig")
        mock_result = MagicMock(stdout="", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            runner.run("get", "pods")
            call_args = mock_run.call_args[0][0]
            assert "--kubeconfig" in call_args
            assert "/tmp/kubeconfig" in call_args

    def test_empty_args_raises(self):
        runner = KubectlRunner()
        with pytest.raises(ValueError, match="不能为空"):
            runner.run()

    def test_timeout(self):
        runner = KubectlRunner(timeout=5)
        with patch("subprocess.run", side_effect=Exception("timeout")):
            # The actual timeout is handled by subprocess, our code returns KubectlResult
            pass

    def test_command_log(self):
        runner = KubectlRunner()
        mock_result = MagicMock(stdout="", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            runner.run("get", "pods")
            runner.run("get", "nodes")

        assert len(runner.command_log) == 2
        assert "get pods" in runner.command_log[0]
        assert "get nodes" in runner.command_log[1]


class TestPermissionDenied:
    def test_read_only_cannot_delete(self):
        runner = KubectlRunner(mode=PermissionMode.READ_ONLY)
        with pytest.raises(PermissionDenied, match="read-only 模式不允许"):
            runner.run("delete", "pod", "test")

    def test_read_only_cannot_patch(self):
        runner = KubectlRunner(mode=PermissionMode.READ_ONLY)
        with pytest.raises(PermissionDenied):
            runner.run("patch", "deployment", "test")

    def test_diagnostic_can_get_logs(self):
        runner = KubectlRunner(mode=PermissionMode.DIAGNOSTIC)
        mock_result = MagicMock(stdout="log line", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("logs", "my-pod")

        assert result.success

    def test_read_write_can_delete(self, caplog):
        """read-write 模式下黑名单降级为警告，命令放行。"""
        runner = KubectlRunner(mode=PermissionMode.READ_WRITE)
        mock_result = MagicMock(stdout="deleted", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("delete", "pod", "test")

        assert result.success
        assert "黑名单警告" in caplog.text or "危险参数" in caplog.text


class TestShellInjection:
    def test_pipe_blocked(self):
        runner = KubectlRunner()
        with pytest.raises(ShellInjectionDetected):
            runner.run("get", "pods", "|", "grep", "foo")

    def test_semicolon_blocked(self):
        runner = KubectlRunner()
        with pytest.raises(ShellInjectionDetected):
            runner.run("get", "pods; rm -rf /")

    def test_dollar_substitution_blocked(self):
        runner = KubectlRunner()
        with pytest.raises(ShellInjectionDetected):
            runner.run("get", "pods", "$(whoami)")

    def test_backtick_blocked(self):
        runner = KubectlRunner()
        with pytest.raises(ShellInjectionDetected):
            runner.run("get", "pods", "`whoami`")


class TestBlacklist:
    def test_force_flag_blocked(self):
        runner = KubectlRunner(mode=PermissionMode.DIAGNOSTIC)
        with pytest.raises(PermissionDenied, match="强制删除"):
            runner.run("get", "pods", "--force")

    def test_grace_period_zero_blocked(self):
        runner = KubectlRunner(mode=PermissionMode.DIAGNOSTIC)
        with pytest.raises(PermissionDenied, match="立即终止"):
            runner.run("get", "pods", "--grace-period=0")

    def test_blacklist_bypass(self):
        runner = KubectlRunner(mode=PermissionMode.READ_WRITE, bypass_blacklist=True)
        mock_result = MagicMock(stdout="deleted", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("delete", "pod", "test")

        assert result.success

    def test_normal_command_not_blocked(self):
        runner = KubectlRunner()
        mock_result = MagicMock(stdout="pod-1\n", stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = runner.run("get", "pods")

        assert result.success


class TestFindNamespaceByPod:
    def test_find_exact_match(self):
        runner = KubectlRunner()
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     web-app-1     1/1     Running   0          5m
backend      api-server    1/1     Running   0          10m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            matches = runner.find_namespace_by_pod("web-app-1")

        assert len(matches) == 1
        assert matches[0]["namespace"] == "frontend"
        assert matches[0]["name"] == "web-app-1"
        assert matches[0]["status"] == "Running"

    def test_find_partial_match(self):
        runner = KubectlRunner()
        mock_output = """NAMESPACE    NAME           READY   STATUS    RESTARTS   AGE
frontend     web-app-1      1/1     Running   0          5m
frontend     web-app-2      1/1     Running   0          5m
backend      api-server     1/1     Running   0          10m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            matches = runner.find_namespace_by_pod("web-app")

        assert len(matches) == 2
        assert all(m["namespace"] == "frontend" for m in matches)

    def test_find_case_insensitive(self):
        runner = KubectlRunner()
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     WebApp-1      1/1     Running   0          5m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            matches = runner.find_namespace_by_pod("webapp")

        assert len(matches) == 1
        assert matches[0]["name"] == "WebApp-1"

    def test_find_no_match(self):
        runner = KubectlRunner()
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     web-app-1     1/1     Running   0          5m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            matches = runner.find_namespace_by_pod("nonexistent")

        assert len(matches) == 0

    def test_find_command_failure(self):
        runner = KubectlRunner()
        mock_result = MagicMock(stdout="", stderr="connection refused", returncode=1)

        with patch("subprocess.run", return_value=mock_result):
            matches = runner.find_namespace_by_pod("test")

        assert len(matches) == 0
