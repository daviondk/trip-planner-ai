"""
Wikipedia search tool for LLM context.

Provides functions to search and fetch Wikipedia articles for use as context
in trip planning and information retrieval.
"""

import httpx
from typing import Literal
import structlog
from app.models.schemas import ToolError, ToolErrorType

logger = structlog.get_logger(__name__)


async def search_wikipedia(
    query: str,
    lang: str = "ru",
    max_results: int = 3
) -> list[dict] | ToolError:
    """
    Search Wikipedia for articles matching the query.
    
    Args:
        query: Search query (city name, POI name, etc.)
        lang: Language code (ru for Russian, en for English)
        max_results: Maximum number of results to return
    
    Returns:
        List of article results with title, description, and URL
    """
    try:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        
        params = {
            "action": "opensearch",
            "format": "json",
            "search": query,
            "limit": max_results,
            "namespace": 0
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Parse results: [query, [titles], [descriptions], [urls]]
            if len(data) < 4:
                return []
            
            results = []
            for title, desc, url in zip(data[1], data[2], data[3]):
                results.append({
                    "title": title,
                    "description": desc,
                    "url": url
                })
            
            logger.info("wikipedia_search_success", query=query, results_count=len(results))
            return results
            
    except httpx.HTTPStatusError as e:
        logger.error("wikipedia_search_http_error", status_code=e.response.status_code)
        return ToolError(
            error_type=ToolErrorType.API_ERROR,
            message=f"Wikipedia API error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error("wikipedia_search_error", error=str(e))
        return ToolError(
            error_type=ToolErrorType.UNKNOWN_ERROR,
            message=f"Wikipedia search failed: {str(e)}"
        )


async def get_wikipedia_page(
    title: str,
    lang: str = "ru",
    summary_only: bool = True
) -> dict | ToolError:
    """
    Get Wikipedia article content for a specific title.
    
    Args:
        title: Article title
        lang: Language code
        summary_only: If True, only get the summary/intro section
    
    Returns:
        Dictionary with title, content, and URL
    """
    try:
        # Get summary via REST API (faster, cleaner)
        if summary_only:
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                
                return {
                    "title": data.get("title", title),
                    "content": data.get("extract", ""),
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "thumbnail": data.get("thumbnail", {}).get("source", "")
                }
        
        # Get full content via Action API
        else:
            url = f"https://{lang}.wikipedia.org/w/api.php"
            
            params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "explaintext": True,
                "exintro": False,
                "titles": title
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                pages = data.get("query", {}).get("pages", {})
                page_id = next(iter(pages.keys()))
                page_data = pages[page_id]
                
                return {
                    "title": page_data.get("title", title),
                    "content": page_data.get("extract", ""),
                    "url": f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                }
            
    except httpx.HTTPStatusError as e:
        logger.error("wikipedia_page_http_error", title=title, status_code=e.response.status_code)
        return ToolError(
            error_type=ToolErrorType.API_ERROR,
            message=f"Wikipedia API error: {e.response.status_code}"
        )
    except Exception as e:
        logger.error("wikipedia_page_error", title=title, error=str(e))
        return ToolError(
            error_type=ToolErrorType.UNKNOWN_ERROR,
            message=f"Failed to fetch Wikipedia page: {str(e)}"
        )


async def search_city_info(
    city: str,
    lang: str = "ru"
) -> dict | ToolError:
    """
    Get information about a city from Wikipedia.
    
    Args:
        city: City name
        lang: Language code
    
    Returns:
        Dictionary with city information
    """
    return await get_wikipedia_page(city, lang, summary_only=True)


async def search_poi_info(
    poi_name: str,
    city: str | None = None,
    lang: str = "ru"
) -> dict | ToolError:
    """
    Get information about a point of interest from Wikipedia.
    
    Args:
        poi_name: POI name
        city: Optional city name for context
        lang: Language code
    
    Returns:
        Dictionary with POI information
    """
    # Try POI name directly first
    result = await get_wikipedia_page(poi_name, lang, summary_only=True)
    
    # If that fails, try with city prefix
    if isinstance(result, ToolError) and city:
        search_query = f"{city} {poi_name}"
        search_results = await search_wikipedia(search_query, lang, max_results=1)
        
        if isinstance(search_results, list) and search_results:
            title = search_results[0]["title"]
            return await get_wikipedia_page(title, lang, summary_only=True)
    
    return result
