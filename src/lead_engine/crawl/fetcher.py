"""HTTP fetcher with rate limiting, retries, and caching."""

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger()


class Fetcher:
    """HTTP fetcher with rate limiting, retries, and caching."""
    
    def __init__(self, config: Dict):
        """
        Initialize fetcher with config.
        
        Args:
            config: Runtime config dict with http, cache, rate_limits sections
        """
        self.config = config
        self.log = logger.bind(component="fetcher")
        
        # HTTP config
        http_config = config.get("http", {})
        self.connect_timeout = http_config.get("connect_timeout_seconds", 5)
        self.read_timeout = http_config.get("read_timeout_seconds", 15)
        self.max_retries = http_config.get("max_retries", 2)
        self.retry_backoff_factor = http_config.get("retry_backoff_factor", 2.0)
        self.user_agents = http_config.get("user_agents", [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        ])
        self.user_agent_index = 0
        
        # Rate limiting config
        rate_config = config.get("rate_limits", {})
        self.per_domain_rps = rate_config.get("per_domain_requests_per_second", 1)
        self.global_rpm = rate_config.get("global_requests_per_minute", 60)
        
        # Cache config
        cache_config = config.get("cache", {})
        self.cache_enabled = True
        self.cache_ttl_hours = cache_config.get("ttl_hours", 24)
        self.cache_dir = Path(cache_config.get("cache_dir", "data/cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Error handling config
        error_config = config.get("error_handling", {})
        self.retry_status_codes = error_config.get("retry_status_codes", [429, 503, 502, 504])
        self.rate_limit_cooldown = error_config.get("rate_limit_cooldown_seconds", 60)
        
        # Rate limiting state
        self.domain_last_request = defaultdict(float)
        self.global_requests = []
        
        # HTTP client
        self.client = httpx.Client(
            timeout=httpx.Timeout(connect=self.connect_timeout, read=self.read_timeout),
            follow_redirects=True,
        )
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def _rate_limit(self, url: str):
        """Apply rate limiting for domain and global."""
        domain = self._get_domain(url)
        current_time = time.time()
        
        # Per-domain rate limiting
        if domain in self.domain_last_request:
            time_since_last = current_time - self.domain_last_request[domain]
            min_interval = 1.0 / self.per_domain_rps
            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                self.log.debug("Rate limiting domain", domain=domain, sleep=sleep_time)
                time.sleep(sleep_time)
        
        self.domain_last_request[domain] = time.time()
        
        # Global rate limiting (sliding window)
        now = time.time()
        self.global_requests = [req_time for req_time in self.global_requests if now - req_time < 60]
        
        if len(self.global_requests) >= self.global_rpm:
            sleep_time = 60 - (now - self.global_requests[0]) + 0.1
            if sleep_time > 0:
                self.log.debug("Global rate limit reached, sleeping", sleep=sleep_time)
                time.sleep(sleep_time)
                # Clean up old requests
                self.global_requests = [req_time for req_time in self.global_requests if now - req_time < 60]
        
        self.global_requests.append(time.time())
    
    def _get_cache_key(self, url: str) -> Path:
        """Get cache file path for URL."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"
    
    def _load_cache(self, url: str) -> Optional[Tuple[int, str, Dict]]:
        """Load from cache if valid."""
        if not self.cache_enabled:
            return None
        
        cache_file = self._get_cache_key(url)
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file) as f:
                cache_data = json.load(f)
            
            # Check TTL
            cached_at = datetime.fromisoformat(cache_data["fetched_at"])
            age = datetime.now() - cached_at
            
            if age > timedelta(hours=self.cache_ttl_hours):
                self.log.debug("Cache expired", url=url, age_hours=age.total_seconds() / 3600)
                cache_file.unlink()
                return None
            
            self.log.debug("Cache hit", url=url)
            return (
                cache_data["status_code"],
                cache_data["html"],
                cache_data["meta"]
            )
        except Exception as e:
            self.log.warning("Error loading cache", url=url, error=str(e))
            return None
    
    def _save_cache(self, url: str, status_code: int, html: str, meta: Dict):
        """Save to cache."""
        if not self.cache_enabled:
            return
        
        cache_file = self._get_cache_key(url)
        try:
            cache_data = {
                "url": url,
                "status_code": status_code,
                "html": html,
                "meta": meta,
                "fetched_at": datetime.now().isoformat(),
            }
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            self.log.warning("Error saving cache", url=url, error=str(e))
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    def _get_user_agent(self) -> str:
        """Get next user agent (rotate)."""
        ua = self.user_agents[self.user_agent_index % len(self.user_agents)]
        self.user_agent_index += 1
        return ua
    
    def fetch(self, url: str, cache_enabled: bool = True) -> Tuple[int, str, Dict]:
        """
        Fetch URL with retries, rate limiting, and caching.
        
        Args:
            url: URL to fetch
            cache_enabled: Whether to use cache
        
        Returns:
            Tuple of (status_code, html_text, response_meta)
            response_meta includes: headers, content_hash, fetched_at, etc.
        """
        # Check cache first
        if cache_enabled:
            cached = self._load_cache(url)
            if cached:
                return cached
        
        # Apply rate limiting
        self._rate_limit(url)
        
        # Retry logic
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                headers = {
                    "User-Agent": self._get_user_agent(),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                }
                
                response = self.client.get(url, headers=headers)
                
                # Handle rate limit responses
                if response.status_code == 429 or response.status_code == 503:
                    self.log.warning("Rate limited, waiting", url=url, status=response.status_code, attempt=attempt + 1)
                    if attempt < self.max_retries:
                        time.sleep(self.rate_limit_cooldown)
                        continue
                    else:
                        raise httpx.HTTPStatusError(
                            f"Rate limited after {self.max_retries + 1} attempts",
                            request=response.request,
                            response=response
                        )
                
                response.raise_for_status()
                
                # Success
                html = response.text
                content_hash = self._compute_content_hash(html)
                
                meta = {
                    "headers": dict(response.headers),
                    "content_hash": content_hash,
                    "fetched_at": datetime.now().isoformat(),
                    "url": str(response.url),
                    "status_code": response.status_code,
                }
                
                # Save to cache
                if cache_enabled:
                    self._save_cache(url, response.status_code, html, meta)
                
                self.log.debug("Fetch successful", url=url, status=response.status_code, size=len(html))
                return response.status_code, html, meta
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code in self.retry_status_codes and attempt < self.max_retries:
                    backoff = self.retry_backoff_factor ** attempt
                    self.log.warning("HTTP error, retrying", url=url, status=e.response.status_code, attempt=attempt + 1, backoff=backoff)
                    time.sleep(backoff)
                    last_exception = e
                    continue
                raise
            except httpx.RequestError as e:
                if attempt < self.max_retries:
                    backoff = self.retry_backoff_factor ** attempt
                    self.log.warning("Request error, retrying", url=url, error=str(e), attempt=attempt + 1, backoff=backoff)
                    time.sleep(backoff)
                    last_exception = e
                    continue
                raise
            except Exception as e:
                self.log.error("Unexpected error fetching", url=url, error=str(e), exc_info=True)
                raise
        
        # If we get here, all retries failed
        if last_exception:
            raise last_exception
        raise Exception(f"Failed to fetch {url} after {self.max_retries + 1} attempts")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.client.close()


def fetch(url: str, *, cache_enabled: bool = True, config: Optional[Dict] = None) -> Tuple[int, str, Dict]:
    """
    Fetch URL with retries, rate limiting, and caching.
    
    Convenience function that creates a Fetcher instance.
    
    Args:
        url: URL to fetch
        cache_enabled: Whether to use cache
        config: Optional config dict (loads from runtime.yaml if not provided)
    
    Returns:
        Tuple of (status_code, html_text, response_meta)
    """
    if config is None:
        # Load default config
        from pathlib import Path
        import yaml
        
        config_path = Path("config/runtime.yaml")
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
        else:
            config = {}
    
    with Fetcher(config) as fetcher:
        return fetcher.fetch(url, cache_enabled=cache_enabled)

