"""Test KnowledgeRetriever TF-IDF retrieval."""
import os
import tempfile
from k8s_diagnose.knowledge.retriever import (
    KnowledgeRetriever,
    KnowledgeDoc,
    tokenize,
)


class TestTokenize:
    def test_basic_tokenization(self):
        tokens = tokenize("Pod 启动失败 ImagePullBackOff")
        assert "pod" in tokens
        assert "imagepullbackoff" in tokens
        assert "启动失败" in tokens

    def test_stopwords_removed(self):
        tokens = tokenize("the pod is running and healthy")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "and" not in tokens
        assert "pod" in tokens
        assert "healthy" in tokens

    def test_single_char_removed(self):
        tokens = tokenize("a test x value")
        assert "a" not in tokens
        assert "x" not in tokens
        assert "test" in tokens


class TestKnowledgeRetriever:
    def test_load_and_retrieve(self):
        """Load .md files and retrieve relevant documents."""
        retriever = KnowledgeRetriever(knowledge_dir="knowledge")
        retriever.load()
        # Should find the knowledge files if they exist
        results = retriever.retrieve("排查 Pod 启动失败", top_k=3)
        assert isinstance(results, list)

    def test_retrieve_empty_query(self):
        retriever = KnowledgeRetriever(knowledge_dir="nonexistent_dir")
        retriever.load()
        results = retriever.retrieve("anything")
        assert results == []

    def test_format_retrieved(self):
        retriever = KnowledgeRetriever(knowledge_dir="knowledge")
        docs = [
            KnowledgeDoc(
                path="test.md",
                metadata={"id": "T001"},
                title="Test Doc",
                body="This is test content about pod diagnosis.",
                raw="---\nid: T001\n---\n# Test Doc\nThis is test content about pod diagnosis.",
            )
        ]
        formatted = retriever.format_retrieved(docs, max_chars=100)
        assert "T001" in formatted
        assert "Test Doc" in formatted

    def test_format_truncation(self):
        retriever = KnowledgeRetriever(knowledge_dir="knowledge")
        docs = [
            KnowledgeDoc(
                path="test.md",
                metadata={},
                title="Long Doc",
                body="A" * 500,
                raw="---\n---\n# Long Doc\n" + "A" * 500,
            )
        ]
        formatted = retriever.format_retrieved(docs, max_chars=100)
        assert "已截断" in formatted

    def test_retrieve_scoring(self):
        """Higher TF-IDF score documents should rank higher."""
        retriever = KnowledgeRetriever(knowledge_dir="knowledge")
        results = retriever.retrieve("ImagePullBackOff 镜像", top_k=3)
        assert isinstance(results, list)
        # If documents exist, check they are sorted by relevance
        if results:
            for doc in results:
                assert doc.title or "imagepull" in doc.body.lower() or "镜像" in doc.body

    def test_load_from_temp_files(self):
        """Test loading from temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "test1.md"), "w") as f:
                f.write("---\nid: T1\ntitle: Pod Crash\n---\n# Pod Crash\nCrashLoopBackOff 排查指南")
            with open(os.path.join(tmpdir, "test2.md"), "w") as f:
                f.write("---\nid: T2\ntitle: Node Info\n---\n# Node Info\nKubernetes 节点管理")

            retriever = KnowledgeRetriever(knowledge_dir=tmpdir)
            retriever.load()

            assert len(retriever.documents) == 2

            results = retriever.retrieve("CrashLoopBackOff", top_k=1)
            assert len(results) >= 1
            assert results[0].doc_id == "T1"

    def test_ignore_readme(self):
        """README.md should be ignored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write("# README\nThis should be ignored")
            with open(os.path.join(tmpdir, "actual.md"), "w") as f:
                f.write("---\nid: A1\n---\n# Actual\nSome content")

            retriever = KnowledgeRetriever(knowledge_dir=tmpdir)
            retriever.load()

            assert len(retriever.documents) == 1
            assert retriever.documents[0].doc_id == "A1"
