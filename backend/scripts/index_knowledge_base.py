"""
Knowledge base indexing script for ChromaDB.

Loads data from scripts/data/ directories, chunks documents, 
generates embeddings via YandexGPT, and upserts to ChromaDB collections.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import List, Dict, Any
import httpx
import chromadb
import structlog
from app.config.settings import settings

logger = structlog.get_logger(__name__)

# Data directories
DATA_DIR = Path(__file__).parent / "data"
DESTINATIONS_DIR = DATA_DIR / "destinations"
POI_DIR = DATA_DIR / "points_of_interest"
TRAVEL_TIPS_DIR = DATA_DIR / "travel_tips"


async def get_embedding(text: str) -> List[float]:
    """Get embedding from YandexGPT."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding",
            headers={
                "Authorization": f"Bearer {settings.YANDEX_GPT_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "modelUri": f"emb://{settings.YANDEX_GPT_FOLDER_ID}/{settings.YANDEX_GPT_EMBEDDING_MODEL}",
                "text": text
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


def chunk_text(text: str, max_tokens: int = 512, overlap: int = 128) -> List[str]:
    """
    Split text into chunks of approximately max_tokens.
    
    Simple implementation - in production use proper tokenizer.
    """
    words = text.split()
    chunks = []
    
    current_chunk = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) > max_tokens * 4:  # Rough estimate: 1 word ≈ 4 chars ≈ 1 token
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                # Keep overlap
                overlap_words = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = overlap_words
                current_length = sum(len(w) for w in overlap_words)
        else:
            current_chunk.append(word)
            current_length += len(word)
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


def load_json_files(directory: Path) -> List[Dict[str, Any]]:
    """Load all JSON files from a directory."""
    data = []
    if not directory.exists():
        logger.warning("directory_not_found", directory=str(directory))
        return data
    
    for file_path in directory.glob("*.json"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data.append(json.load(f))
            logger.info("file_loaded", file=str(file_path))
        except Exception as e:
            logger.error("file_load_error", file=str(file_path), error=str(e))
    
    return data


def load_md_files(directory: Path) -> List[Dict[str, Any]]:
    """Load all Markdown files from a directory."""
    data = []
    if not directory.exists():
        logger.warning("directory_not_found", directory=str(directory))
        return data
    
    for file_path in directory.glob("*.md"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            data.append({
                "title": file_path.stem,
                "content": content,
                "source": "markdown"
            })
            logger.info("file_loaded", file=str(file_path))
        except Exception as e:
            logger.error("file_load_error", file=str(file_path), error=str(e))
    
    return data


async def index_collection(
    client: chromadb.HttpClient,
    collection_name: str,
    data: List[Dict[str, Any]],
    metadata_schema: Dict[str, Any]
) -> None:
    """Index data into a ChromaDB collection."""
    if not data:
        logger.warning("no_data_to_index", collection=collection_name)
        return
    
    # Get or create collection
    collection = client.get_or_create_collection(name=collection_name)
    
    # Process each document
    ids = []
    documents = []
    metadatas = []
    embeddings = []
    
    for item in data:
        title = item.get("title", "Unknown")
        content = item.get("content", item.get("description", ""))
        
        # Chunk the content
        chunks = chunk_text(content)
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{title}_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            
            # Build metadata
            metadata = {
                "title": title,
                "source": item.get("source", "synthetic"),
                "language": "ru",
                "updated_at": "2026-04-13"
            }
            
            # Add schema-specific metadata
            for key, value in metadata_schema.items():
                if key in item:
                    metadata[key] = item[key]
                else:
                    metadata[key] = value
            
            metadatas.append(metadata)
            
            # Get embedding (in batches would be better for production)
            embedding = await get_embedding(chunk)
            embeddings.append(embedding)
    
    # Upsert to ChromaDB
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings
    )
    
    logger.info(
        "collection_indexed",
        collection=collection_name,
        documents_count=len(ids)
    )


async def main():
    """Main indexing function."""
    logger.info("indexing_started")
    
    # Initialize ChromaDB client
    client = chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT
    )
    
    # Index destinations
    logger.info("indexing_destinations")
    destinations_data = load_json_files(DESTINATIONS_DIR) + load_md_files(DESTINATIONS_DIR)
    await index_collection(
        client,
        "destinations",
        destinations_data,
        {
            "category": "general",
            "season": None,
            "budget_level": None
        }
    )
    
    # Index POIs
    logger.info("indexing_poi")
    poi_data = load_json_files(POI_DIR)
    await index_collection(
        client,
        "points_of_interest",
        poi_data,
        {
            "category": "general",
            "season": None,
            "budget_level": None
        }
    )
    
    # Index travel tips
    logger.info("indexing_travel_tips")
    tips_data = load_json_files(TRAVEL_TIPS_DIR) + load_md_files(TRAVEL_TIPS_DIR)
    await index_collection(
        client,
        "travel_tips",
        tips_data,
        {
            "category": "tip",
            "season": None,
            "budget_level": None
        }
    )
    
    logger.info("indexing_completed")


if __name__ == "__main__":
    asyncio.run(main())
