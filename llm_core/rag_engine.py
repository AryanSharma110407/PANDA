# RAG Engine & Embedding Model Loader
# Part of llm_core

_embedding_model = None

def _get_embedding_model():
    """Returns the shared SentenceTransformer, loading it on first call only."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        # We no longer use the os.dup2 redirect hack here as it causes deadlocks 
        # on Windows when building the SentenceTransformer embeddings.
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model
