"""
Data Manager for fetching and caching InSight SEIS data from PDS archive.
"""
import re
from pathlib import Path
from typing import List, Tuple, Optional
from urllib.parse import urlparse
import requests
from obspy import Stream, UTCDateTime, read
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
        # PDS URLs use lowercase for network and station
        network_lower = network.lower()
        station_lower = station.lower()
        url = f"{PDS_BASE_URL}{network_lower}/{data_type}/{station_lower}/{year}/{doy:03d}/"
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
            base_url = url if url.endswith('/') else url + '/'
            
            # Try multiple patterns to handle different HTML structures
            patterns = [
                # Pattern 1: href="filename.mseed" or href='filename.mseed'
                r'href=["\']([^"\']+\.mseed)["\']',
                # Pattern 2: href=filename.mseed (no quotes)
                r'href=([^\s>]+\.mseed)',
                # Pattern 3: <a> tag with href
                r'<a[^>]+href=["\']?([^"\'>\s]+\.mseed)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                for match in matches:
                    # Clean up the match
                    filename = match.strip('"\'')
                    # Skip parent directory links
                    if filename.startswith('../') or filename == '..':
                        continue
                    
                    # Build full URL
                    if filename.startswith('http'):
                        full_url = filename
                    elif filename.startswith('./'):
                        full_url = base_url + filename[2:]
                    elif filename.startswith('/'):
                        # Absolute path from domain root
                        parsed = urlparse(url)
                        full_url = f"{parsed.scheme}://{parsed.netloc}{filename}"
                    else:
                        full_url = base_url + filename
                    
                    mseed_urls.append(full_url)
                
                # If we found matches with this pattern, break
                if mseed_urls:
                    break
            
            # Fallback: if no href patterns worked, search for filenames directly
            if not mseed_urls:
                # Look for filenames ending in .mseed in the HTML
                filename_pattern = r'([a-zA-Z0-9._-]+\.mseed)'
                potential_files = re.findall(filename_pattern, response.text, re.IGNORECASE)
                # Filter to only actual filenames (not parts of URLs or other text)
                for filename in potential_files:
                    # Skip if it looks like part of a URL path
                    if '/' in filename or filename.startswith('.'):
                        continue
                    # Build URL
                    full_url = base_url + filename
                    if full_url not in mseed_urls:
                        mseed_urls.append(full_url)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for mseed_url in mseed_urls:
                if mseed_url not in seen:
                    seen.add(mseed_url)
                    unique_urls.append(mseed_url)
            
            logger.info(f"Found {len(unique_urls)} .mseed files in directory")
            if len(unique_urls) == 0:
                logger.debug(f"HTML response preview (first 1000 chars): {response.text[:1000]}")
            return unique_urls
            
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
    
    def download_mseed_files(self, file_urls: List[str], cache_path: Path, 
                             progress_callback=None) -> List[Path]:
        """
        Download .mseed files to local cache.
        
        Args:
            file_urls: List of URLs to .mseed files
            cache_path: Local directory to save files
            progress_callback: Optional callback function(current, total) for progress updates
        
        Returns:
            List of local file paths for successfully downloaded files
        """
        cache_path.mkdir(parents=True, exist_ok=True)
        downloaded_files = []
        total_files = len(file_urls)
        
        for index, url in enumerate(file_urls, start=1):
            try:
                # Extract filename from URL
                filename = url.split('/')[-1]
                local_path = cache_path / filename
                
                # Skip if already downloaded
                if local_path.exists():
                    logger.info(f"File already cached: {filename}")
                    downloaded_files.append(local_path)
                    # Still report progress for already-cached files
                    if progress_callback:
                        progress_callback(len(downloaded_files), total_files)
                    continue
                
                # Download file
                logger.info(f"Downloading {filename}...")
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                
                # Save to cache
                local_path.write_bytes(response.content)
                downloaded_files.append(local_path)
                logger.info(f"Downloaded {filename}")
                
                # Report progress
                if progress_callback:
                    progress_callback(len(downloaded_files), total_files)
                
            except requests.RequestException as e:
                logger.warning(f"Failed to download {url}: {e}")
                # Continue with other files, but still report progress
                if progress_callback:
                    progress_callback(len(downloaded_files), total_files)
            except Exception as e:
                logger.error(f"Unexpected error downloading {url}: {e}")
                # Continue with other files, but still report progress
                if progress_callback:
                    progress_callback(len(downloaded_files), total_files)
        
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
                    trace_stream = read(str(mseed_file))
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
                       data_type: str = "continuous_waveform", 
                       progress_callback=None, file_count_callback=None) -> Path:
        """
        Fetch data from PDS and cache locally, or load from cache if available.
        
        Args:
            network: Network code
            station: Station code
            year: Year
            doy: Day of year
            data_type: Type of data
            progress_callback: Optional callback function(current, total) for download progress
            file_count_callback: Optional callback function(total) to report total file count
        
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
        
        # Report total file count if callback provided
        if file_count_callback:
            file_count_callback(len(file_urls))
        
        # Download files
        downloaded = self.download_mseed_files(file_urls, cache_path, progress_callback)
        
        if not downloaded:
            raise Exception(f"Failed to download any files from {url}")
        
        logger.info(f"Cached {len(downloaded)} files to {cache_path}")
        return cache_path

