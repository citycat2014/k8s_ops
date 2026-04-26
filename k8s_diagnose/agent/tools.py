"""Kubectl tools for the diagnosis agent.

Each tool wraps a kubectl command and returns formatted output for LLM consumption.
Tools are defined as plain Python functions with a local @tool decorator.
"""
import inspect
import functools
from dataclasses import dataclass
from typing import Any

from k8s_diagnose.k8s_client.kubectl import KubectlRunner
from k8s_diagnose.k8s_client.permissions import PermissionMode


@dataclass
class ToolSpec:
    """A tool the LLM can call by name with arguments."""
    name: str
    description: str
    parameters: dict  # JSON Schema for function parameters
    fn: Any  # The actual Python function


_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _build_parameters(func) -> dict:
    """Build JSON Schema from a function's signature."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for name, param in sig.parameters.items():
        type_hint = param.annotation if param.annotation != inspect.Parameter.empty else str
        prop = {"type": _TYPE_MAP.get(type_hint, "string")}

        if param.default != inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(name)

        properties[name] = prop

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool(func):
    """Decorator that wraps a function as a ToolSpec.

    The function's docstring first line becomes the description.
    The function signature becomes the input JSON Schema.
    """
    doc = func.__doc__ or ""
    description = doc.strip().split("\n")[0]

    return ToolSpec(
        name=func.__name__,
        description=description,
        parameters=_build_parameters(func),
        fn=func,
    )


def tools_to_openai_format(tools: list[ToolSpec]) -> list[dict]:
    """Convert ToolSpec list to OpenAI API tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def execute_tool(tools: list[ToolSpec], name: str, args: dict) -> str:
    """Look up a tool by name and call it with the given arguments."""
    for t in tools:
        if t.name == name:
            return t.fn(**args)
    return f"错误: 未知工具 '{name}'"


def _get_runner() -> KubectlRunner:
    """Create or return shared KubectlRunner instance."""
    global _shared_runner
    if not hasattr(_get_runner, "_shared_runner"):
        _get_runner._shared_runner = KubectlRunner(mode=PermissionMode.DIAGNOSTIC)
    return _get_runner._shared_runner


def _run_kubectl(*args: str, namespace: str = "") -> str:
    """Shared kubectl execution with namespace resolution."""
    runner = _get_runner()
    ns = namespace or runner.namespace
    result = runner.run(*args, "-n", ns)
    return result.stdout if result.success else f"错误: {result.stderr}"


def _format_error(result) -> str:
    """Format error output from KubectlResult."""
    return f"错误: {result.stderr}"


# ──────────────────────────────────────────────
# 通用工具 (17个)
# ──────────────────────────────────────────────


@tool
def kubectl_get_pod(name: str, namespace: str = "", output: str = "yaml") -> str:
    """获取 Pod 完整 YAML 或 JSON 信息。用于查看 Pod 所有配置和状态字段。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "pod", name, "-n", ns, "-o", output)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_describe_pod(name: str, namespace: str = "") -> str:
    """获取 Pod 人类可读的详细信息（含 events）。用于快速定位问题。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("describe", "pod", name, "-n", ns)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_logs(
    name: str,
    namespace: str = "",
    container: str = "",
    previous: bool = False,
    tail: int = 200,
) -> str:
    """获取容器日志。previous=True 获取上次崩溃的日志（CrashLoopBackOff 场景）。"""
    runner = _get_runner()
    ns = namespace or runner.namespace
    args = ["logs", name, "-n", ns, "--tail", str(tail)]
    if container:
        args += ["-c", container]
    if previous:
        args.append("--previous")
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_events(namespace: str = "", field_selector: str = "") -> str:
    """获取 namespace 内事件。可指定 field_selector 过滤（如 reason=FailedScheduling）。"""
    runner = _get_runner()
    ns = namespace or runner.namespace
    args = ["get", "events", "-n", ns, "--sort-by=.lastTimestamp"]
    if field_selector:
        args += ["--field-selector", field_selector]
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_list_pods(
    namespace: str = "", label_selector: str = "", field_selector: str = ""
) -> str:
    """列出 namespace 内所有 Pod。可按 label/field 过滤（如 field_selector=status.phase=Pending）。"""
    runner = _get_runner()
    ns = namespace or runner.namespace
    args = ["get", "pods", "-n", ns, "-o", "wide"]
    if label_selector:
        args += ["-l", label_selector]
    if field_selector:
        args += ["--field-selector", field_selector]
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_describe_node(name: str = "") -> str:
    """获取节点详情（条件、资源容量）。不传节点名则列出所有节点。"""
    args = ["describe", "node"]
    if name:
        args.append(name)
    result = _get_runner().run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_deployment(name: str, namespace: str = "") -> str:
    """获取 Deployment 状态（YAML）。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "deployment", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_replicaset(name: str, namespace: str = "") -> str:
    """获取 ReplicaSet 详情。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "replicaset", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_resource_quotas(namespace: str = "") -> str:
    """查看 namespace 资源配额使用情况。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "resourcequotas", "-n", ns)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_pvc(name: str, namespace: str = "") -> str:
    """查看 PVC 状态。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "pvc", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_endpoints(name: str, namespace: str = "") -> str:
    """查看 Service 后端 Endpoints。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "endpoints", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_configmap(name: str, namespace: str = "") -> str:
    """查看 ConfigMap。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "configmap", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_ingress(name: str, namespace: str = "") -> str:
    """查看 Ingress。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "ingress", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_daemonset(name: str, namespace: str = "") -> str:
    """查看 DaemonSet 状态。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "daemonset", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_statefulset(name: str, namespace: str = "") -> str:
    """查看 StatefulSet 状态。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "statefulset", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_service(name: str, namespace: str = "") -> str:
    """查看 Service 详情。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("get", "service", name, "-n", ns, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_nodes() -> str:
    """列出所有节点及其状态。"""
    result = _get_runner().run("get", "nodes", "-o", "wide")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_find_namespace(pod_pattern: str) -> str:
    """根据 pod 名称（或部分名称）查找其所属的 namespace。支持模糊匹配，返回匹配的 namespace 列表。"""
    runner = _get_runner()
    matches = runner.find_namespace_by_pod(pod_pattern)

    if not matches:
        return f"未找到匹配 '{pod_pattern}' 的 pod"

    if len(matches) == 1:
        pod = matches[0]
        return f"找到 pod: {pod['name']}\nnamespace: {pod['namespace']}\nstatus: {pod['status']}"

    # Multiple matches
    lines = [f"找到 {len(matches)} 个匹配结果:"]
    for pod in matches:
        lines.append(f"  - {pod['namespace']}/{pod['name']} ({pod['status']})")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# CNI 专用工具 (6个)
# ──────────────────────────────────────────────


@tool
def kubectl_get_cni_pods(plugin: str = "") -> str:
    """查看 CNI 插件 Pod 状态。不指定 plugin 时自动检测当前集群使用的 CNI。"""
    runner = _get_runner()
    if not plugin:
        detected = runner.discover_cni_plugin()
        if not detected:
            return "错误: 未检测到 CNI 插件。请手动指定 plugin 参数 (calico-node/cilium/flannel/weave-net)"
        plugin = detected[0]
    result = runner.run(
        "get", "pods", "-n", "kube-system",
        "-l", f"k8s-app={plugin}",
        "-o", "wide",
    )
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_cni_configmap(name: str = "") -> str:
    """查看 CNI 网络配置 ConfigMap。不指定 name 时自动检测当前集群使用的 CNI。"""
    runner = _get_runner()
    if not name:
        detected = runner.discover_cni_plugin()
        if not detected:
            return "错误: 未检测到 CNI 插件。请手动指定 name 参数 (calico-config/cilium-config/kube-flannel-cfg/weave-net)"
        name = detected[1]
    result = runner.run("get", "configmap", name, "-n", "kube-system", "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_cni_logs(pod_name: str = "", plugin: str = "") -> str:
    """查看 CNI 插件日志。不指定 plugin 时自动检测当前集群使用的 CNI。"""
    runner = _get_runner()
    if not plugin:
        detected = runner.discover_cni_plugin()
        if not detected:
            return "错误: 未检测到 CNI 插件。请手动指定 plugin 参数 (calico-node/cilium/flannel/weave-net)"
        plugin = detected[0]
    if not pod_name:
        list_result = runner.run(
            "get", "pods", "-n", "kube-system",
            "-l", f"k8s-app={plugin}",
            "-o", "name",
        )
        if list_result.success and list_result.stdout.strip():
            pod_name = list_result.stdout.strip().split("\n")[0].split("/")[-1]
    if not pod_name:
        return "错误: 未找到 CNI 插件 Pod"
    result = runner.run("logs", "-n", "kube-system", pod_name, "--tail", "100")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_networkpolicy(name: str = "", namespace: str = "") -> str:
    """查看 NetworkPolicy 规则。不传名字则列出所有。"""
    ns = namespace or _get_runner().namespace
    args = ["get", "networkpolicy", "-n", ns]
    if name:
        args.append(name)
    result = _get_runner().run(*args, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_endpoint_slices(name: str = "", namespace: str = "") -> str:
    """查看 EndpointSlice 端点信息。"""
    ns = namespace or _get_runner().namespace
    args = ["get", "endpointslices", "-n", ns]
    if name:
        args.append(name)
    result = _get_runner().run(*args, "-o", "yaml")
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_describe_pod_network(name: str, namespace: str = "") -> str:
    """检查 Pod 网络创建相关 events（NetworkPluginNotReady / CNI 错误）。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("describe", "pod", name, "-n", ns)
    if not result.success:
        return _format_error(result)
    lines = result.stdout.split("\n")
    network_lines = []
    in_events = False
    for line in lines:
        if "Events:" in line:
            in_events = True
        if in_events:
            network_lines.append(line)
    if network_lines:
        return "\n".join(network_lines)
    return "未找到 events 信息"


# ──────────────────────────────────────────────
# Volcano 专用工具 (6个)
# ──────────────────────────────────────────────


@tool
def kubectl_get_podgroup(name: str = "", namespace: str = "") -> str:
    """查看 PodGroup CRD 状态（minAvailable, scheduled）。"""
    runner = _get_runner()
    ns = namespace or runner.namespace
    args = ["get", "podgroup", "-n", ns, "-o", "yaml"]
    if name:
        args.insert(-1, name)
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_queue(name: str = "") -> str:
    """查看 Volcano 队列配置与资源配额。"""
    runner = _get_runner()
    args = ["get", "queue", "-o", "yaml"]
    if name:
        args.insert(-1, name)
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_vcjob(name: str = "", namespace: str = "") -> str:
    """查看 Volcano Job (VCJob) 状态。"""
    runner = _get_runner()
    ns = namespace or runner.namespace
    args = ["get", "vcjob", "-n", ns, "-o", "yaml"]
    if name:
        args.insert(-1, name)
    result = runner.run(*args)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_describe_podgroup(name: str, namespace: str = "") -> str:
    """查看 PodGroup 详细状态 + events。"""
    ns = namespace or _get_runner().namespace
    result = _get_runner().run("describe", "podgroup", name, "-n", ns)
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_volcano_scheduler_config() -> str:
    """查看 Volcano 调度器配置（actions + tiers）。"""
    runner = _get_runner()
    result = runner.run(
        "get", "configmap", "volcano-scheduler-configmap",
        "-n", "volcano-system",
        "-o", "yaml",
    )
    return result.stdout if result.success else _format_error(result)


@tool
def kubectl_get_volcano_scheduler_logs(tail: int = 100) -> str:
    """查看 Volcano 调度器日志。"""
    runner = _get_runner()
    result = runner.run(
        "logs", "-n", "volcano-system",
        "deploy/volcano-scheduler",
        "--tail", str(tail),
    )
    return result.stdout if result.success else _format_error(result)


# ──────────────────────────────────────────────
# 工具注册
# ──────────────────────────────────────────────

ALL_TOOLS = [
    # 通用
    kubectl_get_pod,
    kubectl_describe_pod,
    kubectl_get_logs,
    kubectl_get_events,
    kubectl_list_pods,
    kubectl_describe_node,
    kubectl_get_deployment,
    kubectl_get_replicaset,
    kubectl_get_resource_quotas,
    kubectl_get_pvc,
    kubectl_get_endpoints,
    kubectl_get_configmap,
    kubectl_get_ingress,
    kubectl_get_daemonset,
    kubectl_get_statefulset,
    kubectl_get_service,
    kubectl_get_nodes,
    kubectl_find_namespace,
    # CNI
    kubectl_get_cni_pods,
    kubectl_get_cni_configmap,
    kubectl_get_cni_logs,
    kubectl_get_networkpolicy,
    kubectl_get_endpoint_slices,
    kubectl_describe_pod_network,
    # Volcano
    kubectl_get_podgroup,
    kubectl_get_queue,
    kubectl_get_vcjob,
    kubectl_describe_podgroup,
    kubectl_get_volcano_scheduler_config,
    kubectl_get_volcano_scheduler_logs,
]
