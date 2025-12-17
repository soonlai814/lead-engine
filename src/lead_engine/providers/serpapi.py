"""SerpAPI provider for SERP discovery."""

import time
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()


class SerpAPIError(Exception):
    """SerpAPI specific error."""
    pass


class SerpAPIProvider:
    """SerpAPI provider client."""
    
    def __init__(self, api_key: str, timeout: int = 30):
        """
        Initialize SerpAPI provider.
        
        Args:
            api_key: SerpAPI API key
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError("SerpAPI API key is required")
        
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        self.timeout = timeout
        self.log = logger.bind(provider="serpapi")
        
        # Rate limiting tracking
        self.last_request_time = 0.0
        self.min_request_interval = 0.1  # 100ms between requests
    
    def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute search with query and parameters.
        
        Args:
            query: Search query
            **kwargs: Additional SerpAPI parameters (hl, gl, num, start, etc.)
        
        Returns:
            List of result dictionaries with fields: title, snippet, link, rank
        """
        # Rate limiting
        self._rate_limit()
        
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.api_key,
            **kwargs
        }
        
        self.log.debug("Executing SerpAPI search", query=query, params={k: v for k, v in params.items() if k != "api_key"})
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self.base_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Handle SerpAPI errors
                if "error" in data:
                    error_msg = data.get("error", "Unknown SerpAPI error")
                    self.log.error("SerpAPI error", error=error_msg, query=query)
                    raise SerpAPIError(f"SerpAPI error: {error_msg}")
                
                # Extract organic results
                results = []
                organic_results = data.get("organic_results", [])
                
                for idx, result in enumerate(organic_results, start=1):
                    results.append({
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "link": result.get("link", ""),
                        "rank": idx,
                    })
                
                self.log.info("SerpAPI search completed", query=query, results_count=len(results))
                return results
                
        except httpx.HTTPStatusError as e:
            self.log.error("HTTP error in SerpAPI request", status_code=e.response.status_code, query=query)
            raise SerpAPIError(f"HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            self.log.error("Request error in SerpAPI", error=str(e), query=query)
            raise SerpAPIError(f"Request error: {str(e)}") from e
        except Exception as e:
            self.log.error("Unexpected error in SerpAPI search", error=str(e), query=query, exc_info=True)
            raise
    
    def search_with_pagination(self, query: str, pages: int = 1, results_per_page: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        Execute search with pagination.
        
        Args:
            query: Search query
            pages: Number of pages to fetch
            results_per_page: Results per page (num parameter)
            **kwargs: Additional SerpAPI parameters
        
        Returns:
            Combined list of results from all pages
        """
        all_results = []
        
        for page in range(pages):
            start = page * results_per_page
            
            self.log.debug("Fetching page", query=query, page=page + 1, start=start)
            
            try:
                page_results = self.search(
                    query=query,
                    num=results_per_page,
                    start=start,
                    **kwargs
                )
                
                if not page_results:
                    self.log.info("No more results, stopping pagination", query=query, page=page + 1)
                    break
                
                all_results.extend(page_results)
                
                # Small delay between pages
                if page < pages - 1:
                    time.sleep(0.2)
                    
            except SerpAPIError as e:
                self.log.warning("Error fetching page, stopping pagination", query=query, page=page + 1, error=str(e))
                break
        
        self.log.info("Pagination completed", query=query, total_results=len(all_results), pages_fetched=pages)
        return all_results
    
    def _rate_limit(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


def serp_search(query: str, *, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Execute SerpAPI search and return raw results.
    
    Convenience function that creates a provider instance.
    
    Args:
        query: Search query string
        params: Additional SerpAPI parameters (hl, gl, num, start, etc.)
                Must include 'api_key' in params or set SERPAPI_API_KEY env var
    
    Returns:
        List of raw SERP results with fields: title, snippet, link, rank
    
    Raises:
        SerpAPIError: If API call fails
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    api_key = params.pop("api_key", None) or os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise ValueError("SerpAPI API key required (set SERPAPI_API_KEY env var or pass api_key in params)")
    
    provider = SerpAPIProvider(api_key=api_key)
    return provider.search(query=query, **params)

