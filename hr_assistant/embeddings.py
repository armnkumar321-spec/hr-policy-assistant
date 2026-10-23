"""Local, free embeddings: Chroma's bundled all-MiniLM-L6-v2 (ONNX), wrapped for LangChain.
No API key. The model (~80 MB) is downloaded once on first use and cached."""
from langchain_core.embeddings import Embeddings


class LocalMiniLM(Embeddings):
    def __init__(self):
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        self._fn = DefaultEmbeddingFunction()

    def embed_documents(self, texts):
        return [list(map(float, v)) for v in self._fn(list(texts))]

    def embed_query(self, text):
        return self.embed_documents([text])[0]
