"""Lightweight RAG: TF-IDF retrieval without external dependencies.

No vector DB, no BM25 library — pure Python with yaml + math.
"""
import os
import re
import math
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class KnowledgeDoc:
    """A single knowledge document loaded from a .md file."""
    path: str
    metadata: dict
    title: str
    body: str
    raw: str
    tokens: list[str] = field(default_factory=list)
    tf: dict = field(default_factory=dict)
    doc_id: str = ""

    def __post_init__(self):
        if not self.doc_id and self.metadata.get("id"):
            self.doc_id = self.metadata["id"]
        elif not self.doc_id:
            self.doc_id = os.path.splitext(os.path.basename(self.path))[0]


# Common English stop words
_STOP_WORDS = frozenset("""
a an the is are was were be been being have has had do does did will would shall
should may might can could of in to for on with at by from as into about between
through during before after above below up down out off over under and or but not
no yes if so then than both each every all any some this that these those it its he
she they them their his her we our you your me i my
""".strip().split())


def tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, remove stopwords."""
    words = re.findall(r'[a-zA-Z0-9一-鿿]+', text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


class KnowledgeRetriever:
    """TF-IDF based knowledge retriever.

    Usage:
        retriever = KnowledgeRetriever(knowledge_dir="knowledge")
        retriever.load()
        results = retriever.retrieve("排查 Pod 启动失败", top_k=3)
    """

    def __init__(self, knowledge_dir: str, max_injected_chars: int = 4000):
        self.knowledge_dir = knowledge_dir
        self.max_injected_chars = max_injected_chars
        self.documents: list[KnowledgeDoc] = []
        self.idf: dict[str, float] = {}

    def load(self) -> None:
        """Load all .md files from knowledge directory."""
        if not os.path.isdir(self.knowledge_dir):
            return
        for root, _, files in os.walk(self.knowledge_dir):
            for fname in sorted(files):
                if fname.endswith(".md") and fname != "README.md":
                    path = os.path.join(root, fname)
                    doc = self._load_file(path)
                    if doc:
                        self.documents.append(doc)
        self._build_index()

    @staticmethod
    def _parse_frontmatter(raw: str) -> tuple[dict, str, str]:
        """Parse YAML frontmatter from markdown. Returns (metadata, title, body)."""
        meta: dict = {}
        title = ""
        body = raw

        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                import yaml
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    meta = {}
                body = parts[2].strip()

        # Extract title from first # heading
        lines = body.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                title = line[2:].strip()
                break
        if not title and meta.get("title"):
            title = meta["title"]

        return meta, title, body

    def _load_file(self, path: str) -> KnowledgeDoc | None:
        """Load a single .md file."""
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        meta, title, body = self._parse_frontmatter(raw)
        tokens = tokenize(body)
        tf = self._compute_tf(tokens)

        return KnowledgeDoc(
            path=path,
            metadata=meta,
            title=title,
            body=body,
            raw=raw,
            tokens=tokens,
            tf=tf,
        )

    @staticmethod
    def _compute_tf(tokens: list[str]) -> dict[str, int]:
        """Compute term frequency for a document."""
        tf: dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        return dict(tf)

    def _build_index(self) -> None:
        """Build IDF index from all loaded documents."""
        num_docs = len(self.documents)
        if num_docs == 0:
            return

        doc_freq: dict[str, int] = defaultdict(int)
        for doc in self.documents:
            seen = set(doc.tf.keys())
            for term in seen:
                doc_freq[term] += 1

        self.idf = {
            term: math.log((num_docs + 1) / (freq + 1)) + 1
            for term, freq in doc_freq.items()
        }

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        min_score: float = 0.01,
    ) -> list[KnowledgeDoc]:
        """Retrieve top-K documents matching the query.

        Uses TF-IDF scoring. Returns documents sorted by relevance score.
        """
        query_tokens = tokenize(query)
        if not query_tokens or not self.documents:
            return []

        # Compute query TF
        query_tf = self._compute_tf(query_tokens)

        # Score each document
        scores: list[tuple[float, KnowledgeDoc]] = []
        for doc in self.documents:
            score = 0.0
            for term, freq in query_tf.items():
                if term in doc.tf and term in self.idf:
                    score += freq * self.idf[term] * doc.tf[term]
            if score > 0:
                scores.append((score, doc))

        # Sort by score descending
        scores.sort(key=lambda x: -x[0])

        # Filter by min_score and limit
        results = [
            doc for s, doc in scores
            if s >= min_score
        ][:top_k]

        return results

    def format_retrieved(
        self, docs: list[KnowledgeDoc], max_chars: int | None = None
    ) -> str:
        """Format retrieved documents for LLM injection."""
        max_chars = max_chars or self.max_injected_chars
        parts = []
        for doc in docs:
            section = f"### [{doc.doc_id}] {doc.title}\n{doc.body}"
            parts.append(section)

        full = "\n\n".join(parts)
        if len(full) > max_chars:
            full = full[:max_chars] + "\n\n... (内容已截断)"
        return full
