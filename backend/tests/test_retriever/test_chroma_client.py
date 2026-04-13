import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.retriever.chroma_client import ChromaRetriever
from app.models.schemas import RetrievalResult, PlaceMetadata


@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB client."""
    with patch('app.retriever.chroma_client.chromadb.HttpClient') as mock:
        instance = Mock()
        mock.return_value = instance
        instance.get_collection = Mock()
        yield instance


@pytest.fixture
def retriever(mock_chroma_client):
    """Create retriever instance with mocked ChromaDB."""
    return ChromaRetriever()


class TestChromaRetriever:
    """Test suite for ChromaRetriever."""
    
    def test_build_metadata_filter(self, retriever):
        """Test metadata filter building."""
        filter_empty = retriever._build_metadata_filter()
        assert filter_empty == {}
        
        filter_city = retriever._build_metadata_filter(city="Moscow")
        assert filter_city == {"city": "Moscow"}
        
        filter_full = retriever._build_metadata_filter(
            city="Moscow",
            country="Russia",
            category="museum",
            season="summer",
            budget_level="medium"
        )
        assert filter_full == {
            "city": "Moscow",
            "country": "Russia",
            "category": "museum",
            "season": "summer",
            "budget_level": "medium"
        }
    
    def test_deduplicate_results(self, retriever):
        """Test result deduplication by title."""
        results = [
            RetrievalResult(
                score=0.9,
                title="Red Square",
                text="Description 1",
                source="wikipedia",
                metadata=PlaceMetadata(
                    city="Moscow",
                    country="Russia",
                    category="museum"
                )
            ),
            RetrievalResult(
                score=0.8,
                title="Red Square",
                text="Description 2",
                source="osm",
                metadata=PlaceMetadata(
                    city="Moscow",
                    country="Russia",
                    category="museum"
                )
            ),
            RetrievalResult(
                score=0.7,
                title="Kremlin",
                text="Description 3",
                source="wikipedia",
                metadata=PlaceMetadata(
                    city="Moscow",
                    country="Russia",
                    category="museum"
                )
            )
        ]
        
        deduplicated = retriever._deduplicate_results(results)
        assert len(deduplicated) == 2
        assert deduplicated[0].title == "Red Square"
        assert deduplicated[0].score == 0.9  # Keep highest score
        assert deduplicated[1].title == "Kremlin"
    
    @pytest.mark.asyncio
    async def test_search_places_basic(self, retriever, mock_chroma_client):
        """Test basic search functionality."""
        # Mock collection
        mock_collection = Mock()
        mock_chroma_client.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            'ids': [['doc1', 'doc2']],
            'distances': [[0.1, 0.2]],  # Similarity = 1 - distance
            'metadatas': [[
                {
                    'title': 'Red Square',
                    'city': 'Moscow',
                    'country': 'Russia',
                    'category': 'museum',
                    'source': 'wikipedia'
                },
                {
                    'title': 'Kremlin',
                    'city': 'Moscow',
                    'country': 'Russia',
                    'category': 'museum',
                    'source': 'wikipedia'
                }
            ]],
            'documents': [['Description of Red Square', 'Description of Kremlin']]
        }
        
        # Mock embedding
        with patch.object(retriever, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            
            results = await retriever.search_places(
                query="museums in Moscow",
                collection="points_of_interest",
                limit=10
            )
            
            assert len(results) == 2
            assert results[0].title == "Red Square"
            assert results[0].score > 0.8  # 1 - 0.1
            assert results[0].metadata.city == "Moscow"
    
    @pytest.mark.asyncio
    async def test_search_places_with_filters(self, retriever, mock_chroma_client):
        """Test search with metadata filters."""
        mock_collection = Mock()
        mock_chroma_client.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            'ids': [['doc1']],
            'distances': [[0.1]],
            'metadatas': [[{'title': 'Test', 'city': 'Moscow', 'country': 'Russia', 'category': 'museum', 'source': 'wikipedia'}]],
            'documents': [['Test description']]
        }
        
        with patch.object(retriever, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            
            results = await retriever.search_places(
                query="museums",
                collection="points_of_interest",
                city="Moscow",
                category="museum",
                limit=10
            )
            
            # Verify filter was passed to query
            call_args = mock_collection.query.call_args
            where_filter = call_args.kwargs.get('where')
            assert where_filter == {'city': 'Moscow', 'category': 'museum'}
    
    @pytest.mark.asyncio
    async def test_search_places_score_threshold(self, retriever, mock_chroma_client):
        """Test score threshold filtering."""
        mock_collection = Mock()
        mock_chroma_client.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            'ids': [['doc1', 'doc2', 'doc3']],
            'distances': [[0.1, 0.6, 0.8]],  # Similarities: 0.9, 0.4, 0.2
            'metadatas': [[
                {'title': 'High', 'city': 'Moscow', 'country': 'Russia', 'category': 'museum', 'source': 'wikipedia'},
                {'title': 'Medium', 'city': 'Moscow', 'country': 'Russia', 'category': 'museum', 'source': 'wikipedia'},
                {'title': 'Low', 'city': 'Moscow', 'country': 'Russia', 'category': 'museum', 'source': 'wikipedia'}
            ]],
            'documents': [['Desc1', 'Desc2', 'Desc3']]
        }
        
        with patch.object(retriever, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            
            results = await retriever.search_places(
                query="museums",
                collection="points_of_interest",
                limit=10,
                score_threshold=0.5  # Only first result should pass
            )
            
            assert len(results) == 1
            assert results[0].title == "High"
    
    @pytest.mark.asyncio
    async def test_search_places_empty_results(self, retriever, mock_chroma_client):
        """Test handling of empty results."""
        mock_collection = Mock()
        mock_chroma_client.get_collection.return_value = mock_collection
        mock_collection.query.return_value = {
            'ids': [[]],
            'distances': [[]],
            'metadatas': [[]],
            'documents': [[]]
        }
        
        with patch.object(retriever, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            
            results = await retriever.search_places(
                query="nonexistent place",
                collection="points_of_interest",
                limit=10
            )
            
            assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_search_places_invalid_collection_fallback(self, retriever, mock_chroma_client):
        """Test fallback to default collection on invalid collection."""
        mock_collection = Mock()
        mock_chroma_client.get_collection.side_effect = [Exception("Not found"), mock_collection]
        mock_collection.query.return_value = {
            'ids': [[]],
            'distances': [[]],
            'metadatas': [[]],
            'documents': [[]]
        }
        
        with patch.object(retriever, '_get_embedding', new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            
            results = await retriever.search_places(
                query="test",
                collection="invalid_collection",
                limit=10
            )
            
            # Should have fallen back to points_of_interest
            assert mock_chroma_client.get_collection.call_count == 2
