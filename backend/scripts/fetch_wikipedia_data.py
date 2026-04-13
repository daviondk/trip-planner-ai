"""
Wikipedia data fetcher for Trip Planner AI knowledge base.

Fetches articles about Russian cities and points of interest from Wikipedia,
formats them according to the data schema, and saves to data/ directories.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List
import httpx
import structlog

logger = structlog.get_logger(__name__)

# Data directories
DATA_DIR = Path(__file__).parent / "data"
DESTINATIONS_DIR = DATA_DIR / "destinations"
POI_DIR = DATA_DIR / "points_of_interest"
TRAVEL_TIPS_DIR = DATA_DIR / "travel_tips"

# Russian cities to fetch
CITIES = [
    "Москва",
    "Санкт-Петербург",
    "Казань",
    "Новосибирск",
    "Екатеринбург",
    "Нижний Новгород",
    "Самара",
    "Омск",
    "Челябинск",
    "Ростов-на-Дону",
    "Уфа",
    "Красноярск",
    "Воронеж",
    "Пермь",
    "Волгоград",
    "Краснодар",
    "Саратов",
    "Тюмень",
    "Тольятти",
    "Ижевск",
    "Барнаул",
    "Иркутск",
    "Ульяновск",
    "Киров",
    "Чебоксары",
    "Оренбург",
    "Тула",
    "Пенза",
    "Калининград",
    "Суздаль",
    "Владимир",
    "Ярославль",
    "Смоленск",
    "Псков",
    "Великий Новгород",
    "Мурманск",
    "Архангельск",
    "Владивосток",
    "Хабаровск",
    "Сочи"
]

# Popular POIs to fetch
POIS = [
    ("Москва", "Кремль"),
    ("Москва", "Красная площадь"),
    ("Москва", "Большие театр"),
    ("Москва", "Третьяковская галерея"),
    ("Санкт-Петербург", "Эрмитаж"),
    ("Санкт-Петербург", "Исаакиевский собор"),
    ("Санкт-Петербург", "Дворцовая площадь"),
    ("Санкт-Петербург", "Мариинский театр"),
    ("Казань", "Казанский Кремль"),
    ("Казань", "Храм всех религий"),
    ("Великий Новгород", "Новгородский Кремль"),
    ("Великий Новгород", "Софийский собор"),
    ("Владимир", "Успенский собор"),
    ("Владимир", "Золотые ворота"),
    ("Суздаль", "Кремль"),
    ("Суздаль", "Спасо-Евфимиев монастырь"),
    ("Ярославль", "Спасо-Преображенский собор"),
    ("Мурманск", "Атомный ледокол Ленин"),
    ("Владивосток", "Русский мост"),
    ("Сочи", "Красная Поляна")
]


async def fetch_wikipedia_summary(title: str, lang: str = "ru") -> str:
    """
    Fetch article summary from Wikipedia API.
    
    Args:
        title: Article title
        lang: Language code (ru for Russian Wikipedia)
    
    Returns:
        Article summary text
    """
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Get extract (summary)
            extract = data.get("extract", "")
            return extract
            
    except httpx.HTTPStatusError as e:
        logger.warning("wikipedia_not_found", title=title, status=e.response.status_code)
        return ""
    except Exception as e:
        logger.error("wikipedia_fetch_error", title=title, error=str(e))
        return ""


async def fetch_wikipedia_page_content(title: str, lang: str = "ru") -> str:
    """
    Fetch full article content from Wikipedia API.
    
    Args:
        title: Article title
        lang: Language code
    
    Returns:
        Article content text
    """
    url = f"https://{lang}.wikipedia.org/w/api.php"
    
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "explaintext": True,
        "exintro": True,
        "titles": title
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            pages = data.get("query", {}).get("pages", {})
            page_id = next(iter(pages.keys()))
            page_data = pages[page_id]
            
            extract = page_data.get("extract", "")
            return extract
            
    except Exception as e:
        logger.error("wikipedia_content_error", title=title, error=str(e))
        return ""


async def save_destination(city: str) -> bool:
    """
    Fetch and save city data as destination.
    
    Args:
        city: City name
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Fetch Wikipedia summary
        summary = await fetch_wikipedia_summary(city)
        
        if not summary:
            logger.warning("no_summary_for_city", city=city)
            return False
        
        # Create destination data
        data = {
            "title": city,
            "description": summary,
            "category": "general",
            "season": "summer",
            "budget_level": "medium",
            "source": "wikipedia"
        }
        
        # Save to file
        filename = city.lower().replace(" ", "_") + ".json"
        filepath = DESTINATIONS_DIR / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info("destination_saved", city=city, file=str(filepath))
        return True
        
    except Exception as e:
        logger.error("destination_save_error", city=city, error=str(e))
        return False


async def save_poi(city: str, poi_name: str) -> bool:
    """
    Fetch and save POI data.
    
    Args:
        city: City name
        poi_name: POI name
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Fetch Wikipedia summary
        summary = await fetch_wikipedia_summary(poi_name)
        
        if not summary:
            logger.warning("no_summary_for_poi", poi=poi_name)
            return False
        
        # Create POI data
        data = {
            "title": poi_name,
            "description": summary,
            "category": "museum",
            "season": "summer",
            "budget_level": "medium",
            "source": "wikipedia",
            "rating": 4.5,
            "coordinates": [0.0, 0.0]  # Would need geocoding to get real coordinates
        }
        
        # Save to file
        filename = poi_name.lower().replace(" ", "_").replace("-", "_") + ".json"
        filepath = POI_DIR / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info("poi_saved", poi=poi_name, city=city, file=str(filepath))
        return True
        
    except Exception as e:
        logger.error("poi_save_error", poi=poi_name, error=str(e))
        return False


async def main():
    """Main function to fetch and save Wikipedia data."""
    logger.info("wikipedia_fetch_started")
    
    # Ensure directories exist
    DESTINATIONS_DIR.mkdir(parents=True, exist_ok=True)
    POI_DIR.mkdir(parents=True, exist_ok=True)
    TRAVEL_TIPS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Fetch cities
    logger.info("fetching_cities", count=len(CITIES))
    cities_success = 0
    for city in CITIES:
        if await save_destination(city):
            cities_success += 1
    
    # Fetch POIs
    logger.info("fetching_pois", count=len(POIS))
    pois_success = 0
    for city, poi in POIS:
        if await save_poi(city, poi):
            pois_success += 1
    
    logger.info(
        "wikipedia_fetch_completed",
        cities_success=cities_success,
        cities_total=len(CITIES),
        pois_success=pois_success,
        pois_total=len(POIS)
    )


if __name__ == "__main__":
    asyncio.run(main())
