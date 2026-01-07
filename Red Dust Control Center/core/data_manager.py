"""
Data Manager for fetching and caching InSight SEIS data from PDS archive.
"""
import re
from pathlib import Path
from typing import List, Tuple, Optional
import requests
from obspy import Stream, UTCDateTime
import logging

logger = logging.getLogger(__name__)

# Base URL for InSight SEIS PDS archive
PDS_BASE_URL = "https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/"


class DataManager:
    """Manages fetching, downloading, and caching of seismic waveform data."""
    
    def __init__(self, cache_root: Path = Path("cache")):
        """
        Initialize DataManager.
        
        Args:
            cache_root: Root directory for local cache storage
        """
        self.cache_root = Path(cache_root)
        self.cache_root.mkdir(parents=True, exist_ok=True)
    
    def build_pds_url(self, network: str, station: str, year: int, doy: int, 
                     data_type: str = "continuous_waveform") -> str:
        """
        Build PDS archive URL for the specified data.
        
        Args:
            network: Network code (e.g., "XB")
            station: Station code (e.g., "ELYSE", "ELYS0", "ELYHK", "ELYH0")
            year: Year (e.g., 2019)
            doy: Day of year (1-366)
            data_type: Type of data ("continuous_waveform" or "event_waveform")
        
        Returns:
            Full URL to PDS directory
        """
        url = f"{PDS_BASE_URL}data/{network}/{data_type}/{station}/{year}/{doy:03d}/"
        return url
    
    def fetch_directory_listing(self, url: str) -> List[str]:
        """
        Fetch directory listing from PDS archive and extract .mseed file URLs.
        
        Args:
            url: PDS directory URL
        
        Returns:
            List of full URLs to .mseed files
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Parse HTML to find .mseed file links
            mseed_urls = []
            # Look for links ending in .mseed
            pattern = r'href="([^"]+\.mseed)"'
            matches = re.findall(pattern, response.text)
            
            for match in matches:
                # Handle relative and absolute URLs
                if match.startswith('http'):
                    mseed_urls.append(match)
                else:
                    # Ensure URL ends with / before appending relative path
                    base_url = url if url.endswith('/') else url + '/'
                    mseed_urls.append(base_url + match)
            
            logger.info(f"Found {len(mseed_urls)} .mseed files in directory")
            return mseed_urls
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch directory listing from {url}: {e}")
            return []
    
    def get_cache_path(self, network: str, station: str, year: int, doy: int,
                      data_type: str = "continuous_waveform") -> Path:
        """
        Get local cache path for specified data (mirrors PDS structure).
        
        Args:
            network: Network code
            station: Station code
            year: Year
            doy: Day of year
            data_type: Type of data
        
        Returns:
            Path to cache directory
        """
        cache_path = self.cache_root / "data" / network / data_type / station / str(year) / f"{doy:03d}"
        return cache_path
    
    def is_cached(self, network: str, station: str, year: int, doy: int,
                  data_type: str = "continuous_waveform") -> bool:
        """
        Check if data is already cached locally.
        
        Args:
            network: Network code
            station: Station code
            year: Year
            doy: Day of year
            data_type: Type of data
        
        Returns:
            True if cache directory exists and contains .mseed files
        """
        cache_path = self.get_cache_path(network, station, year, doy, data_type)
        if not cache_path.exists():
            return False
        
        # Check for .mseed files
        mseed_files = list(cache_path.glob("*.mseed"))
        return len(mseed_files) > 0
    
    def download_mseed_files(self, file_urls: List[str], cache_path: Path) -> List[Path]:
        """
        Download .mseed files to local cache.
        
        Args:
            file_urls: List of URLs to .mseed files
            cache_path: Local directory to save files
        
        Returns:
            List of local file paths for successfully downloaded files
        """
        cache_path.mkdir(parents=True, exist_ok=True)
        downloaded_files = []
        
        for url in file_urls:
            try:
                # Extract filename from URL
                filename = url.split('/')[-1]
                local_path = cache_path / filename
                
                # Skip if already downloaded
                if local_path.exists():
                    logger.info(f"File already cached: {filename}")
                    downloaded_files.append(local_path)
                    continue
                
                # Download file
                logger.info(f"Downloading {filename}...")
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                
                # Save to cache
                local_path.write_bytes(response.content)
                downloaded_files.append(local_path)
                logger.info(f"Downloaded {filename}")
                
            except requests.RequestException as e:
                logger.warning(f"Failed to download {url}: {e}")
                # Continue with other files
            except Exception as e:
                logger.error(f"Unexpected error downloading {url}: {e}")
        
        return downloaded_files
    
    def load_from_cache(self, cache_path: Path) -> Stream:
        """
        Load waveform data from local cache using ObsPy.
        
        Args:
            cache_path: Path to directory containing .mseed files
        
        Returns:
            ObsPy Stream containing all channels
        
        Raises:
            FileNotFoundError: If no .mseed files found
            ValueError: If data cannot be parsed
        """
        if not cache_path.exists():
            raise FileNotFoundError(f"Cache directory does not exist: {cache_path}")
        
        mseed_files = list(cache_path.glob("*.mseed"))
        if not mseed_files:
            raise FileNotFoundError(f"No .mseed files found in {cache_path}")
        
        logger.info(f"Loading {len(mseed_files)} .mseed files from cache...")
        
        try:
            # Load all files into a single stream
            stream = Stream()
            for mseed_file in mseed_files:
                try:
                    trace_stream = Stream.read(str(mseed_file))
                    stream += trace_stream
                except Exception as e:
                    logger.warning(f"Failed to parse {mseed_file.name}: {e}")
                    # Skip corrupted files
            
            if len(stream) == 0:
                raise ValueError("No valid traces loaded from cache")
            
            # Merge traces when possible (same network, station, location, channel)
            stream.merge(method=1)  # Method 1: fill gaps with NaN
            
            logger.info(f"Loaded stream with {len(stream)} traces")
            return stream
            
        except Exception as e:
            logger.error(f"Failed to load data from cache: {e}")
            raise
    
    def fetch_and_cache(self, network: str, station: str, year: int, doy: int,
                       data_type: str = "continuous_waveform") -> Path:
        """
        Fetch data from PDS and cache locally, or load from cache if available.
        
        Args:
            network: Network code
            station: Station code
            year: Year
            doy: Day of year
            data_type: Type of data
        
        Returns:
            Path to cache directory
        
        Raises:
            Exception: If fetching or caching fails
        """
        cache_path = self.get_cache_path(network, station, year, doy, data_type)
        
        # Check if already cached
        if self.is_cached(network, station, year, doy, data_type):
            logger.info(f"Using cached data for {network}/{station}/{year}/{doy:03d}")
            return cache_path
        
        # Fetch from PDS
        logger.info(f"Fetching data from PDS for {network}/{station}/{year}/{doy:03d}...")
        url = self.build_pds_url(network, station, year, doy, data_type)
        file_urls = self.fetch_directory_listing(url)
        
        if not file_urls:
            raise Exception(f"No .mseed files found at {url}")
        
        # Download files
        downloaded = self.download_mseed_files(file_urls, cache_path)
        
        if not downloaded:
            raise Exception(f"Failed to download any files from {url}")
        
        logger.info(f"Cached {len(downloaded)} files to {cache_path}")
        return cache_path

