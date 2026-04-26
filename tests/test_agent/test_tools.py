"""Tests for agent tools."""
import pytest
from unittest.mock import patch, MagicMock

from k8s_diagnose.agent.tools import (
    kubectl_find_namespace,
    execute_tool,
    ALL_TOOLS,
)


class TestKubectlFindNamespace:
    def test_single_match(self):
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     web-app-1     1/1     Running   0          5m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_find_namespace.fn("web-app-1")

        assert "web-app-1" in result
        assert "frontend" in result
        assert "Running" in result

    def test_multiple_matches(self):
        mock_output = """NAMESPACE    NAME           READY   STATUS    RESTARTS   AGE
frontend     web-app-1      1/1     Running   0          5m
frontend     web-app-2      1/1     Running   0          5m
backend      api-server     1/1     Running   0          10m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_find_namespace.fn("web-app")

        assert "2 个匹配结果" in result
        assert "frontend/web-app-1" in result
        assert "frontend/web-app-2" in result

    def test_no_match(self):
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     web-app-1     1/1     Running   0          5m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = kubectl_find_namespace.fn("nonexistent")

        assert "未找到匹配" in result


class TestToolRegistration:
    def test_find_namespace_in_all_tools(self):
        tool_names = [t.name for t in ALL_TOOLS]
        assert "kubectl_find_namespace" in tool_names

    def test_execute_find_namespace_tool(self):
        mock_output = """NAMESPACE    NAME          READY   STATUS    RESTARTS   AGE
frontend     test-pod      1/1     Running   0          5m
"""
        mock_result = MagicMock(stdout=mock_output, stderr="", returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = execute_tool(ALL_TOOLS, "kubectl_find_namespace", {"pod_pattern": "test-pod"})

        assert "test-pod" in result
        assert "frontend" in result
