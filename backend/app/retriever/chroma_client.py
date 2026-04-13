import chromadb
from chromadb.config import Settings
import httpx
from typing import Optional
import structlog
from prometheus_client import Counter, Histogram
from app.config.settings import settings
from app.models.schemas import RetrievalResult, PlaceMetadata
from app.utils.langfuse_client import langfuse_client
from app.utils.llm_client import get_llm_client

logger = structlog.get_logger(__name__)

# Prometheus metrics
retriever_search_total = Counter(
    'retriever_search_total',
    'Total retriever searches',
    ['collection', 'status']
)

retriever_search_duration_seconds = Histogram(
    'retriever_search_duration_seconds',
    'Retriever search duration',
    ['collection', 'rerank']
)

retriever_results_count = Histogram(
    'retriever_results_count',
    'Number of results returned',
    ['collection']
)

retriever_errors_total = Counter(
    'retriever_errors_total',
    'Total retriever errors',
    ['error_type']
)

retriever_score_distribution = Histogram(
    'retriever_score_distribution',
    'Score distribution of results',
    ['collection']
)


class ChromaRetriever:
    """ChromaDB retriever for semantic search of travel information."""
    
    def __init__(self):
        self.client = None
        self._connect()
    
    def _connect(self):
        """Connect to ChromaDB."""
        try:
            self.client = chromadb.HttpClient(
                host=settings.CHROMA_HOST,
                port=settings.CHROMA_PORT,
                settings=Settings(allow_reset=True, anonymized_telemetry=False)
            )
            logger.info("chroma_connected", host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        except Exception as e:
            logger.error("chroma_connection_failed", error=str(e))
            # Don't raise - set client to None for degraded mode
            self.client = None
    
    def _get_embedding(self, text: str) -> list[float]:
        """Get embedding from configured LLM provider."""
        with langfuse_client.observe(
            name="embedding_generation",
            input={"text": text[:100]},
            metadata={"provider": settings.LLM_PROVIDER}
        ) as span:
            try:
                llm_client = get_llm_client()
                embedding = llm_client.get_embedding(text)

                if embedding is None:
                    retriever_errors_total.labels(error_type="embedding_failed").inc()
                    logger.error("embedding_failed", query=text[:50])
                    span.end(output={"error": "embedding_failed"})
                    raise ValueError("Failed to generate embedding")

                span.end(output={"embedding_dim": len(embedding)})
                return embedding
            except Exception as e:
                retriever_errors_total.labels(error_type="embedding_error").inc()
                logger.error("embedding_error", error=str(e))
                span.end(output={"error": str(e)})
                raise
    
    def _build_metadata_filter(
        self,
        city: Optional[str] = None,
        country: Optional[str] = None,
        category: Optional[str] = None,
        season: Optional[str] = None,
        budget_level: Optional[str] = None
    ) -> dict:
        """Build ChromaDB where filter from parameters."""
        filters = {}
        if city:
            filters["city"] = city
        if country:
            filters["country"] = country
        if category:
            filters["category"] = category
        if season:
            filters["season"] = season
        if budget_level:
            filters["budget_level"] = budget_level
        return filters
    
    def _deduplicate_results(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Remove duplicates by title, keeping highest score."""
        seen = {}
        for result in results:
            if result.title not in seen or result.score > seen[result.title].score:
                seen[result.title] = result
        return list(seen.values())
    
    def search_places(
        self,
        query: str,
        collection: str = "points_of_interest",
        city: Optional[str] = None,
        country: Optional[str] = None,
        category: Optional[str] = None,
        season: Optional[str] = None,
        budget_level: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.5,
        rerank: bool = False
    ) -> list[RetrievalResult]:
        """
        Semantic search for places in ChromaDB.

        Args:
            query: Search query text
            collection: ChromaDB collection name
            city: Filter by city
            country: Filter by country
            category: Filter by category
            season: Filter by season
            budget_level: Filter by budget level
            limit: Max results to return
            score_threshold: Minimum similarity score
            rerank: Whether to use LLM reranking (not implemented in PoC)

        Returns:
            List of RetrievalResult objects
        """
        if self.client is None:
            logger.warning("chroma_not_connected", query=query[:50])
            retriever_search_total.labels(collection=collection, status='error').inc()
            retriever_errors_total.labels(error_type="no_client").inc()
            return []
        import time
        start_time = time.time()

        with langfuse_client.observe(
            name="retrieval_search",
            input={
                "query": query[:100],
                "collection": collection,
                "filters": {"city": city, "category": category, "budget_level": budget_level}
            },
            metadata={"limit": limit, "score_threshold": score_threshold, "rerank": rerank}
        ) as span:
            try:
                # Validate collection exists, fallback to default
                try:
                    self.client.get_collection(name=collection)
                except:
                    logger.warning("invalid_collection", collection=collection, fallback="points_of_interest")
                    collection = "points_of_interest"
                    self.client.get_collection(name=collection)

                # Get query embedding
                query_embedding = self._get_embedding(query)
                
                # Build metadata filter
                where_filter = self._build_metadata_filter(city, country, category, season, budget_level)
                
                # Search in ChromaDB
                chroma_collection = self.client.get_collection(name=collection)
                search_results = chroma_collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit * 2,  # Get more for deduplication
                    where=where_filter if where_filter else None
                )
                
                # Process results
                retrieval_results = []
                if search_results['ids'] and search_results['ids'][0]:
                    for i, doc_id in enumerate(search_results['ids'][0]):
                        score = 1.0 - search_results['distances'][0][i]  # Convert distance to similarity
                        if score < score_threshold:
                            continue
                        
                        metadata = search_results['metadatas'][0][i]
                        text = search_results['documents'][0][i]
                        
                        # Create PlaceMetadata
                        place_metadata = PlaceMetadata(
                            city=metadata.get('city', ''),
                            country=metadata.get('country', ''),
                            category=metadata.get('category', 'general'),
                            season=metadata.get('season'),
                            budget_level=metadata.get('budget_level'),
                            rating=metadata.get('rating'),
                            coordinates=metadata.get('coordinates')
                        )
                        
                        result = RetrievalResult(
                            score=score,
                            title=metadata.get('title', doc_id),
                            text=text,
                            source=metadata.get('source', 'synthetic'),
                            metadata=place_metadata
                        )
                        retrieval_results.append(result)
                        
                        retriever_score_distribution.labels(collection=collection).observe(score)
                
                # Deduplicate by title
                deduplicated = self._deduplicate_results(retrieval_results)
                
                # Limit results
                final_results = deduplicated[:limit]
                
                duration = time.time() - start_time
                retriever_search_duration_seconds.labels(collection=collection, rerank=rerank).observe(duration)
                retriever_search_total.labels(collection=collection, status='success').inc()
                retriever_results_count.labels(collection=collection).observe(len(final_results))
                
                logger.info(
                    "search_completed",
                    collection=collection,
                    query_length=len(query),
                    results_count=len(final_results),
                    duration_ms=duration * 1000,
                    filters=where_filter
                )
                
                span.end(output={
                    "results_count": len(final_results),
                    "duration_ms": duration * 1000,
                    "status": "success"
                })
                
                return final_results
                
            except Exception as e:
                duration = time.time() - start_time
                retriever_search_duration_seconds.labels(collection=collection, rerank=rerank).observe(duration)
                retriever_search_total.labels(collection=collection, status='error').inc()
                retriever_errors_total.labels(error_type="search_error").inc()
                
                logger.error(
                    "search_failed",
                    collection=collection,
                    error=str(e),
                    duration_ms=duration * 1000
                )
                
                span.end(output={
                    "error": str(e),
                    "duration_ms": duration * 1000,
                    "status": "error"
                })
                
                # Return empty list on error (degraded mode)
                return []


# Global retriever instance
retriever = ChromaRetriever()
