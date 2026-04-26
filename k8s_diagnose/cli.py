"""Typer CLI for k8s-diagnose."""
import typer
import asyncio

from k8s_diagnose.config import Config, K8sConfig
from k8s_diagnose.agent.orchestrator import DiagnoseAgent

app = typer.Typer(
    help="K8s 运维诊断智能体 — 排查 Pod 启动失败、调度失败、CNI 网络异常、Volcano 调度问题",
    add_completion=False,
)


@app.command()
def diagnose(
    query: str = typer.Argument(..., help="诊断问题描述"),
    namespace: str = typer.Option("default", "-n", "--namespace", help="K8s 命名空间"),
    mode: str = typer.Option(
        "read-only",
        "--mode",
        help="权限模式: read-only | diagnostic | read-write",
    ),
    kubeconfig: str = typer.Option(None, "--kubeconfig", help="kubeconfig 路径"),
    show_thoughts: bool = typer.Option(True, "--show-thoughts/--no-thoughts", help="显示排查思维链"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互模式"),
    config_file: str = typer.Option(None, "--config", help="配置文件路径 (YAML)"),
):
    """K8s 运维诊断智能体"""
    if config_file:
        config = Config.from_yaml(config_file)
    else:
        config = Config()
        config.k8s = K8sConfig(
            default_namespace=namespace,
            kubeconfig=kubeconfig,
            mode=mode,
        )
        config.agent.show_thoughts = show_thoughts

    async def _run(query: str):
        agent = DiagnoseAgent(config)
        result = await agent.run(query, namespace=config.k8s.default_namespace)
        typer.echo(result)

    if interactive:
        typer.echo("K8s 诊断智能体已启动。输入 'exit' 退出。")
        while True:
            try:
                user_input = typer.prompt(">>> ")
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.strip().lower() in ("exit", "quit", "q"):
                break
            if not user_input.strip():
                continue
            asyncio.run(_run(user_input))
    else:
        asyncio.run(_run(query))


if __name__ == "__main__":
    app()
