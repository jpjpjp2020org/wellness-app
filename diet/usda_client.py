import requests
from django.core.cache import cache
from decouple import config
from typing import Optional, Dict, Any
import logging
from requests.exceptions import RequestException
from time import sleep
import hashlib
import json

logger = logging.getLogger(__name__)

class USDAClient:
    """Client for interacting with the USDA FoodData Central API"""
    
    def __init__(self):
        self.api_key = config('USDA_API_KEY')
        self.base_url = 'https://api.nal.usda.gov/fdc/v1'
        self.rate_limit_wait = 1  # seconds to wait between requests
        
    def _create_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """
        Create a safe cache key from the endpoint and parameters
        """
        # drop API key from params for cache key
        cache_params = params.copy()
        cache_params.pop('api_key', None)
        
        # deterministic string representation of parameters
        param_str = json.dumps(cache_params, sort_keys=True)
        
        # MD5 hash of the parameters
        param_hash = hashlib.md5(param_str.encode()).hexdigest()
        
        # safe cache key
        return f"usda_api_{endpoint}_{param_hash}"
        
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict]:
        """
        Make a request to the USDA API with error handling and rate limiting
        """
        if params is None:
            params = {}
            
        # API key to params
        params['api_key'] = self.api_key
        
        cache_key = self._create_cache_key(endpoint, params)
        
        # Check cache first
        cached_response = cache.get(cache_key)
        if cached_response:
            return cached_response
            
        try:
            # ratelimiting
            sleep(self.rate_limit_wait)
            
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # cahce success responses for 1 hour
            cache.set(cache_key, data, 3600)
            
            return data
            
        except RequestException as e:
            logger.error(f"USDA API request failed: {str(e)}")
            return None
            
    def search_foods(self, query: str, page: int = 1, page_size: int = 25) -> Optional[Dict]:
        """
        Search for foods in the USDA database with pagination support
        
        Args:
            query (str): Search query
            page (int): Page number (1-based)
            page_size (int): Number of results per page
            
        Returns:
            Optional[Dict]: Search results with pagination info
        """
        params = {
            'query': query,
            'pageSize': page_size,
            'pageNumber': page - 1,  # USDA API uses 0-based pagination or something
            'dataType': ["Foundation", "SR Legacy"]  # higher quality data sources
        }
        return self._make_request('foods/search', params)
        
    def get_food_details(self, fdc_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific food
        
        This endpoint returns much more detailed nutritional information including:
        - Detailed nutrient breakdown
        - Serving size information
        - Data source and quality indicators
        - Scientific name and classification
        - And more
        
        Args:
            fdc_id (str): The FDC ID of the food item
            
        Returns:
            Optional[Dict]: Detailed food information
        """
        params = {
            'format': 'full'  # get all - dropping some later likley if know all use cases and needs
        }
        return self._make_request(f'food/{fdc_id}', params)
        
    def test_connection(self) -> bool:
        """
        Test the API connection with a simple query
        """
        try:
            result = self.search_foods('apple', page_size=1)
            return result is not None and 'foods' in result
        except Exception as e:
            logger.error(f"USDA API connection test failed: {str(e)}")
            return False 