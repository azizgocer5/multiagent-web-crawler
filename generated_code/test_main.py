import asyncio
import pytest
from database import Database
from indexer import Crawler
from search import SearchEngine

@pytest.mark.asyncio
async def test_full_integration():
    db = Database("test.db")
    await db.initialize()
    
    crawler = Crawler("https://example.com", db, max_depth=1)
    search_engine = SearchEngine("test.db")
    
    # Verify crawl triggers DB update
    await crawler.process_page("https://example.com")
    
    # Verify search reads correct DB
    results = await search_engine.search("example")
    assert len(results) > 0
    assert results[0]['url'] == "https://example.com"