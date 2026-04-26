"""Test thought chain."""
from k8s_diagnose.agent.thought_chain import ThoughtChain, ThoughtType


class TestThoughtChain:
    def test_add_and_render(self):
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "Pod Phase=Pending")
        chain.add(ThoughtType.HYPOTHESIS, "调度失败")
        chain.add(ThoughtType.VERIFICATION, "events 显示 Insufficient memory")
        chain.add(ThoughtType.CONCLUSION, "集群内存不足")

        assert len(chain.nodes) == 4
        rendered = chain.render()
        assert "排查思维链" in rendered
        assert "Pod Phase=Pending" in rendered

    def test_to_llm_context(self):
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "看到 X")
        chain.add(ThoughtType.HYPOTHESIS, "假设 Y")

        context = chain.to_llm_context()
        assert "[观察] 看到 X" in context
        assert "[假设] 假设 Y" in context

    def test_last_node(self):
        chain = ThoughtChain()
        assert chain.last_node is None

        chain.add(ThoughtType.OBSERVATION, "test")
        assert chain.last_node is not None
        assert chain.last_node.content == "test"

    def test_with_tool_info(self):
        chain = ThoughtChain()
        chain.add(
            ThoughtType.ACTION,
            "获取 Pod 信息",
            tool_called="kubectl get pod test",
            tool_result_summary="Phase=Pending",
        )
        node = chain.last_node
        assert node.tool_called == "kubectl get pod test"
        assert node.tool_result_summary == "Phase=Pending"

    def test_compressed_context_pairs_action_observation(self):
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "用户请求: pod my-pod 启动失败")
        chain.add(
            ThoughtType.ACTION,
            "调用工具 kubectl_describe_pod",
            tool_called="kubectl_describe_pod(ns=default, name=my-pod)",
        )
        chain.add(ThoughtType.OBSERVATION, "Pod 状态 Waiting")
        chain.add(ThoughtType.HYPOTHESIS, "可能是镜像名称错误")

        ctx = chain.to_compressed_llm_context()
        assert "> 用户请求: pod my-pod 启动失败" in ctx
        assert "调用工具 kubectl_describe_pod → Pod 状态 Waiting" in ctx
        assert "? 可能是镜像名称错误" in ctx

    def test_compressed_context_standalone_observation(self):
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "初始问题描述")

        ctx = chain.to_compressed_llm_context()
        assert "> 初始问题描述" in ctx

    def test_compressed_context_all_types(self):
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "obs")
        chain.add(ThoughtType.HYPOTHESIS, "hyp")
        chain.add(ThoughtType.VERIFICATION, "ver")
        chain.add(ThoughtType.CONCLUSION, "con")

        ctx = chain.to_compressed_llm_context()
        assert "> obs" in ctx
        assert "? hyp" in ctx
        assert "→ ver" in ctx
        assert "✓ con" in ctx

    def test_compressed_vs_original_shorter(self):
        """Compression reduces length in realistic scenarios with tool calls."""
        chain = ThoughtChain()
        chain.add(ThoughtType.OBSERVATION, "用户请求: my-api pod 一直 ImagePullBackOff")
        chain.add(
            ThoughtType.ACTION,
            "调用工具 kubectl_describe_pod",
            tool_called="kubectl_describe_pod(ns=prod, name=my-api-xk2mn)",
        )
        chain.add(ThoughtType.OBSERVATION, "Pod Waiting, Reason=ImagePullBackOff, 镜像拉取失败")
        chain.add(ThoughtType.HYPOTHESIS, "可能是镜像 tag 不存在或私有仓库缺少认证")
        chain.add(
            ThoughtType.ACTION,
            "调用工具 kubectl_get_pod",
            tool_called="kubectl_get_pod(ns=prod, selector=app=my-api)",
        )
        chain.add(
            ThoughtType.OBSERVATION,
            "NAME=my-api-xk2mn STATUS=ImagePullBackOff IP=10.244.1.15 NODE=worker-01",
        )

        compressed = chain.to_compressed_llm_context()
        original = chain.to_llm_context()
        assert len(compressed) < len(original)
