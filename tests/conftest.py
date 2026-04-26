"""Test conftest with kubectl mock fixtures."""
from unittest.mock import patch, MagicMock
import pytest


def mock_kubectl(*args):
    """Mock kubectl subprocess.run for testing."""
    mock = MagicMock()
    cmd = " ".join(args) if args else ""

    # Default: return empty success
    mock.stdout = ""
    mock.stderr = ""
    mock.returncode = 0

    return mock


@pytest.fixture
def mock_subprocess():
    """Provide mock subprocess.run that returns successful empty results."""
    with patch("subprocess.run", return_value=mock_kubectl()) as m:
        yield m


@pytest.fixture
def mock_kubectl_runner():
    """Mock subprocess in k8s_client.kubectl module."""
    with patch("k8s_diagnose.k8s_client.kubectl.subprocess.run") as m:
        m.return_value = mock_kubectl()
        yield m
