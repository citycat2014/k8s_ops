# 变更日志

## v0.1.1 (2026-04-26)

### 新增知识库文档

- **Volcano GPU 调度故障排查** (`knowledge/error-patterns/volcano-gpu-scheduling.md`)
  - Gang 调度死锁诊断与解决
  - GPU 配额不足排查
  - vGPU 内存分配失败处理
  - GPU 碎片化问题优化
  - 优先级抢占失败分析

## v0.1.0 (2026-04-26)

### 技术栈变更

- **LLM 框架**: ~~LangChain + LangGraph~~ → 原生 OpenAI API
  - 理由: 减少依赖，代码更简洁可控
  - 实现: 直接使用 `openai.AsyncOpenAI`，原生 ReAct 循环

- **知识检索**: ~~BM25/向量数据库~~ → TF-IDF (纯 Python)
  - 理由: 轻量级，无外部服务依赖
  - 实现: `knowledge/retriever.py` 基于 TF-IDF 算法

### 新增功能

- 上下文压缩 (`context_compression`): 思维链 token 使用量减少 40-50%
- 敏感参数拦截: 禁止 `--kubeconfig`, `--server`, `--token` 等参数
- 知识库检索: TF-IDF 检索 `knowledge/` 目录文档，注入 LLM 上下文

### 工具数量

- 29 个 kubectl 工具（17 通用 + 6 CNI + 6 Volcano）

### 安全增强

- 4 层安全校验:
  1. 子命令白名单
  2. Shell 注入检测
  3. 敏感参数拦截（新增）
  4. 关键字黑名单
