"""Configuration management with Pydantic + YAML."""
from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1
    api_key: str = ""
    base_url: str = ""


class K8sConfig(BaseModel):
    kubeconfig: str | None = None
    default_namespace: str = "default"
    mode: str = "read-only"
    bypass_blacklist: bool = False


class AgentConfig(BaseModel):
    max_tool_calls: int = 20
    timeout_seconds: int = 120
    show_thoughts: bool = True
    context_compression: bool = True


class KnowledgeConfig(BaseModel):
    enabled: bool = True
    knowledge_dir: str = "knowledge"
    max_results: int = 3
    min_score: float = 0.01
    max_injected_chars: int = 4000


class Config(BaseModel):
    llm: LLMConfig = LLMConfig()
    k8s: K8sConfig = K8sConfig()
    agent: AgentConfig = AgentConfig()
    knowledge: KnowledgeConfig = KnowledgeConfig()

    @staticmethod
    def from_yaml(path: str) -> "Config":
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return Config(**data) if data else Config()
