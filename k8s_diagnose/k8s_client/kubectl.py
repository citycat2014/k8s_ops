"""Kubectl command runner with permission enforcement and audit logging."""
import subprocess
import re
import logging
from dataclasses import dataclass, field

from k8s_diagnose.k8s_client.permissions import (
    PermissionMode,
    ALLOWED_KUBECTL_COMMANDS,
    GLOBAL_BLACKLIST,
    RESTRICTED_KEYWORDS,
)

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """Raised when a command violates permission policy."""
    pass


class ShellInjectionDetected(Exception):
    """Raised when shell metacharacters are detected in arguments."""
    pass


@dataclass
class KubectlResult:
    stdout: str
    stderr: str
    returncode: int
    command: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


# Shell metacharacter pattern
_SHELL_META_PATTERN = re.compile(r'[|;&$`]|\$\(|`')

# Parameters that can override cluster/auth context
_SENSITIVE_PARAMS = frozenset([
    "--kubeconfig", "--server", "--token",
    "--certificate-authority", "--as", "--as-group",
])


@dataclass
class KubectlRunner:
    """Executes kubectl commands with permission checking and audit logging."""

    kubeconfig: str | None = None
    namespace: str = "default"
    mode: PermissionMode = PermissionMode.READ_ONLY
    bypass_blacklist: bool = False
    timeout: int = 30

    _command_log: list[str] = field(default_factory=list, init=False)

    def _check_subcommand(self, subcommand: str) -> None:
        allowed = ALLOWED_KUBECTL_COMMANDS.get(self.mode, set())
        if subcommand not in allowed:
            raise PermissionDenied(
                f"{self.mode} 模式不允许执行 '{subcommand}' 命令"
            )

    def _check_shell_injection(self, args: tuple[str, ...]) -> None:
        for arg in args:
            if _SHELL_META_PATTERN.search(arg):
                raise ShellInjectionDetected(
                    f"检测到 shell 注入字符: '{arg}'"
                )

    def _check_sensitive_params(self, args: tuple[str, ...]) -> None:
        for arg in args:
            key = arg.split("=")[0] if "=" in arg else arg
            if key in _SENSITIVE_PARAMS:
                raise PermissionDenied(f"禁止使用敏感参数: {arg}")

    def _check_blacklist(self, args: tuple[str, ...]) -> None:
        if self.bypass_blacklist:
            return
        full_args = " ".join(args)
        for keyword, reason in GLOBAL_BLACKLIST:
            if keyword in full_args:
                raise PermissionDenied(
                    f"命令包含危险参数 '{keyword}'（{reason}），被全局黑名单拦截"
                )
        if self.mode != PermissionMode.READ_WRITE:
            for keyword, reason in RESTRICTED_KEYWORDS:
                if keyword in full_args:
                    raise PermissionDenied(
                        f"命令包含危险参数 '{keyword}'（{reason}），{self.mode} 模式下被拦截"
                    )

    def run(self, *args: str) -> KubectlResult:
        """
        Execute a kubectl command.
        Usage: runner.run("get", "pod", "my-pod", "-n", "default", "-o", "yaml")
        """
        if not args:
            raise ValueError("kubectl 命令不能为空")

        # Permission checks
        self._check_subcommand(args[0])
        self._check_shell_injection(args)
        self._check_sensitive_params(args)
        self._check_blacklist(args)

        # Build command
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd += ["--kubeconfig", self.kubeconfig]
        cmd += ["-n", self.namespace, *args]

        command_str = " ".join(cmd)

        # Execute
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return KubectlResult(
                stdout="",
                stderr=f"命令超时 ({self.timeout}s): {command_str}",
                returncode=-1,
                command=command_str,
            )

        self._command_log.append(command_str)

        return KubectlResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            command=command_str,
        )

    @property
    def command_log(self) -> list[str]:
        return list(self._command_log)

    def discover_cni_plugin(self) -> tuple[str, str] | None:
        """Auto-discover the CNI plugin running in the cluster.

        Returns (daemonset_label, configmap_name) or None if no CNI detected.
        """
        for label, config in _CNI_DETECT_MAP.items():
            result = self.run(
                "get", "daemonset", "-n", "kube-system",
                "-l", f"k8s-app={label}",
            )
            if result.success and result.stdout.strip():
                return (label, config)
        return None

    def find_namespace_by_pod(self, pod_pattern: str) -> list[dict[str, str]]:
        """Find namespace(s) by pod name pattern.

        Searches across all namespaces for pods matching the given pattern.
        Returns a list of dicts with 'namespace', 'name', 'status' keys.

        Args:
            pod_pattern: Pod name or partial name to search for

        Returns:
            List of matching pod info dicts, empty list if none found
        """
        result = self.run("get", "pods", "-A", "-o", "wide")
        if not result.success:
            return []

        matches = []
        lines = result.stdout.strip().split("\n")

        # Skip header line and parse
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue

            namespace = parts[0]
            pod_name = parts[1]
            status = parts[3]

            if pod_pattern.lower() in pod_name.lower():
                matches.append({
                    "namespace": namespace,
                    "name": pod_name,
                    "status": status,
                })

        return matches


# Known CNI DaemonSet labels and their ConfigMap names
_CNI_DETECT_MAP = {
    "calico-node": "calico-config",
    "cilium": "cilium-config",
    "kube-flannel-ds": "kube-flannel-cfg",
    "weave-net": "weave-net",
}
