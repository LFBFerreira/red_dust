"""
Data Manager for fetching and caching InSight SEIS data from PDS archive.
"""
import re
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from urllib.parse import urlparse
import requests
from obspy import Stream, UTCDateTime, read
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
        self.metadata_cache_path = self.cache_root / "metadata.json"
        self._metadata_cache: Dict = self._load_metadata_cache()
    
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
    
    def fetch_directory_names(self, url: str, filter_years: bool = False) -> List[str]:
        """
        Fetch directory listing from PDS archive and extract directory names.
        
        Args:
            url: PDS directory URL
            filter_years: If True, exclude 4-digit numbers (years) - use when fetching days
        
        Returns:
            List of directory names (years or days of year)
        """
        try:
            logger.debug(f"Fetching directory listing from: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            logger.debug(f"Response status: {response.status_code}, Content length: {len(response.text)}")
            
            # Parse HTML to find directory links (typically end with /)
            directory_names = []
            base_url = url if url.endswith('/') else url + '/'
            
            # Multiple patterns to match different HTML structures
            # Apache directory listings can vary in format
            patterns = [
                # Pattern 1: href="dirname/" or href='dirname/'
                r'href=["\']([^"\']+/)"',
                # Pattern 2: href=dirname/ (no quotes)
                r'href=([^\s>]+/)',
                # Pattern 3: <a> tag with href ending in /
                r'<a[^>]+href=["\']?([^"\'>\s]+/)',
                # Pattern 4: Look for links that are just numbers (more flexible)
                r'href=["\']?(\d+)/?["\']?',
                # Pattern 5: Directory entries in table format
                r'<a[^>]*href=["\']?([^"\'>\s]*(\d+)[^"\'>\s]*/?)["\']?',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                for match in matches:
                    # Handle tuple matches (from pattern 5)
                    if isinstance(match, tuple):
                        match = match[0] if match[0] else match[1]
                    
                    # Clean up the match
                    dirname = match.strip('"\'/')
                    
                    # Skip parent directory and empty names
                    if dirname in ['..', '.', ''] or dirname.startswith('../'):
                        continue
                    # Skip if it's a full URL
                    if dirname.startswith('http'):
                        continue
                    # Extract just the numeric part if there's extra text
                    # Some links might be like "2018/" or "2018" or "data/2018/"
                    numeric_match = re.search(r'(\d+)', dirname)
                    if numeric_match:
                        dirname = numeric_match.group(1)
                    
                    # Should be numeric (year or day of year)
                    if dirname.isdigit():
                        # Filter out years (4-digit numbers) when fetching days
                        if filter_years and len(dirname) == 4:
                            continue
                        directory_names.append(dirname)
                
                if directory_names:
                    break
            
            # If still no matches, try a more aggressive approach
            if not directory_names:
                # Look for any 4-digit numbers (years) or 1-3 digit numbers (days)
                # in href attributes
                all_hrefs = re.findall(r'href=["\']?([^"\'>\s]+)["\'>\s]', response.text, re.IGNORECASE)
                for href in all_hrefs:
                    href = href.strip('"\'/')
                    # Extract numeric directory names
                    if '/' in href:
                        parts = href.split('/')
                        for part in parts:
                            if part.isdigit():
                                # Filter out years when fetching days
                                if filter_years and len(part) == 4:
                                    continue
                                if part not in directory_names:
                                    directory_names.append(part)
                    elif href.isdigit():
                        # Filter out years when fetching days
                        if filter_years and len(href) == 4:
                            continue
                        if href not in directory_names:
                            directory_names.append(href)
            
            # Remove duplicates and sort
            unique_dirs = sorted(set(directory_names), key=lambda x: int(x))
            
            if not unique_dirs:
                # Debug: log a sample of the HTML to see what we're dealing with
                logger.debug(f"No directories found. HTML sample (first 2000 chars):\n{response.text[:2000]}")
            
            return unique_dirs
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch directory listing from {url}: {e}")
            return []
    
    def _load_metadata_cache(self) -> Dict:
        """Load metadata cache from disk."""
        if self.metadata_cache_path.exists():
            try:
                with open(self.metadata_cache_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load metadata cache: {e}")
        return {}
    
    def _save_metadata_cache(self) -> None:
        """Save metadata cache to disk."""
        try:
            with open(self.metadata_cache_path, 'w') as f:
                json.dump(self._metadata_cache, f, indent=2)
        except IOError as e:
            logger.error(f"Failed to save metadata cache: {e}")
    
    def get_available_years(self, network: str, station: str, 
                           data_type: str = "continuous_waveform",
                           use_cache: bool = True) -> List[int]:
        """
        Get available years for a station.
        
        Args:
            network: Network code
            station: Station code
            data_type: Type of data
            use_cache: Whether to use cached data if available
        
        Returns:
            List of available years (sorted)
        """
        cache_key = f"{network.lower()}/{station.lower()}/years"
        
        # Check cache first
        if use_cache and cache_key in self._metadata_cache:
            cached_years = self._metadata_cache[cache_key]
            logger.info(f"Using cached years for {network}/{station}: {len(cached_years)} years found")
            return [int(y) for y in cached_years]
        
        # Fetch from PDS
        network_lower = network.lower()
        station_lower = station.lower()
        url = f"{PDS_BASE_URL}{network_lower}/{data_type}/{station_lower}/"
        
        logger.info(f"Fetching available years from PDS for {network}/{station}...")
        year_strings = self.fetch_directory_names(url)
        years = [int(y) for y in year_strings]
        
        # Cache the result
        self._metadata_cache[cache_key] = year_strings
        self._save_metadata_cache()
        
        logger.info(f"Found {len(years)} available years for {network}/{station}: {years[:5]}{'...' if len(years) > 5 else ''}")
        return years
    
    def get_available_days(self, network: str, station: str, year: int,
                          data_type: str = "continuous_waveform",
                          use_cache: bool = True) -> List[int]:
        """
        Get available days of year for a station and year.
        
        Args:
            network: Network code
            station: Station code
            year: Year
            data_type: Type of data
            use_cache: Whether to use cached data if available
        
        Returns:
            List of available days of year (sorted)
        """
        cache_key = f"{network.lower()}/{station.lower()}/{year}/days"
        
        # Check cache first
        if use_cache and cache_key in self._metadata_cache:
            cached_days = self._metadata_cache[cache_key]
            logger.info(f"Using cached days for {network}/{station}/{year}: {len(cached_days)} days found")
            return [int(d) for d in cached_days]
        
        # Fetch from PDS
        network_lower = network.lower()
        station_lower = station.lower()
        url = f"{PDS_BASE_URL}{network_lower}/{data_type}/{station_lower}/{year}/"
        
        logger.info(f"Fetching available days from PDS for {network}/{station}/{year}...")
        day_strings = self.fetch_directory_names(url, filter_years=True)
        days = [int(d) for d in day_strings]
        
        # Cache the result
        self._metadata_cache[cache_key] = day_strings
        self._save_metadata_cache()
        
        logger.info(f"Found {len(days)} available days for {network}/{station}/{year}")
        return days
    
    def refresh_metadata_cache(self, network: str, station: str,
                              data_type: str = "continuous_waveform") -> None:
        """
        Refresh metadata cache for a station by fetching from PDS.
        
        Args:
            network: Network code
            station: Station code
            data_type: Type of data
        """
        logger.info(f"Refreshing metadata cache for {network}/{station}...")
        # Fetch years (this will also cache them)
        logger.info("Step 1/2: Fetching available years...")
        years = self.get_available_years(network, station, data_type, use_cache=False)
        logger.info(f"Step 1/2 complete: Found {len(years)} years")
        
        # Fetch days for each year
        logger.info(f"Step 2/2: Fetching available days for {len(years)} years...")
        total_days = 0
        for i, year in enumerate(years, 1):
            days = self.get_available_days(network, station, year, data_type, use_cache=False)
            total_days += len(days)
            logger.info(f"  Year {year}: {len(days)} days ({i}/{len(years)})")
        
        logger.info(f"Metadata cache refresh complete for {network}/{station}: {len(years)} years, {total_days} total days")
    
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
        Download .mseed files to local cache using parallel threads.
        
        Args:
            file_urls: List of URLs to .mseed files
            cache_path: Local directory to save files
            progress_callback: Optional callback function(current, total) for progress updates
        
        Returns:
            List of local file paths for successfully downloaded files
        """
        cache_path.mkdir(parents=True, exist_ok=True)
        total_files = len(file_urls)
        downloaded_files = []
        downloaded_lock = threading.Lock()
        progress_counter = 0
        progress_lock = threading.Lock()
        
        def download_single_file(url: str) -> Optional[Path]:
            """Download a single file and return its local path, or None on failure."""
            nonlocal progress_counter
            
            try:
                # Extract filename from URL
                filename = url.split('/')[-1]
                local_path = cache_path / filename
                
                # Skip if already downloaded
                if local_path.exists():
                    # Get file size for logging
                    file_size = local_path.stat().st_size
                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.2f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.2f} MB"
                    logger.info(f"File already cached: {filename} ({size_str})")
                    with downloaded_lock:
                        downloaded_files.append(local_path)
                    # Update progress counter
                    with progress_lock:
                        progress_counter += 1
                        if progress_callback:
                            progress_callback(progress_counter, total_files)
                    return local_path
                
                # Download file
                logger.info(f"Downloading {filename}...")
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                
                # Save to cache
                local_path.write_bytes(response.content)
                
                # Get file size for logging
                file_size = local_path.stat().st_size
                if file_size < 1024:
                    size_str = f"{file_size} B"
                elif file_size < 1024 * 1024:
                    size_str = f"{file_size / 1024:.2f} KB"
                else:
                    size_str = f"{file_size / (1024 * 1024):.2f} MB"
                
                logger.info(f"Downloaded {filename} ({size_str})")
                
                # Add to downloaded list
                with downloaded_lock:
                    downloaded_files.append(local_path)
                
                # Update progress counter
                with progress_lock:
                    progress_counter += 1
                    if progress_callback:
                        progress_callback(progress_counter, total_files)
                
                return local_path
                
            except requests.RequestException as e:
                logger.warning(f"Failed to download {url}: {e}")
                # Update progress counter even on failure
                with progress_lock:
                    progress_counter += 1
                    if progress_callback:
                        progress_callback(progress_counter, total_files)
                return None
            except Exception as e:
                logger.error(f"Unexpected error downloading {url}: {e}")
                # Update progress counter even on failure
                with progress_lock:
                    progress_counter += 1
                    if progress_callback:
                        progress_callback(progress_counter, total_files)
                return None
        
        # Download files in parallel using 5 threads
        logger.info(f"Starting parallel download of {total_files} files using 5 threads...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit all download tasks
            future_to_url = {executor.submit(download_single_file, url): url for url in file_urls}
            
            # Process completed downloads as they finish
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    # Result is already handled in download_single_file
                except Exception as e:
                    logger.error(f"Exception in download thread for {url}: {e}")
        
        logger.info(f"Parallel download complete: {len(downloaded_files)}/{total_files} files downloaded")
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
        import time
        start_time = time.time()
        
        if not cache_path.exists():
            raise FileNotFoundError(f"Cache directory does not exist: {cache_path}")
        
        mseed_files = list(cache_path.glob("*.mseed"))
        if not mseed_files:
            raise FileNotFoundError(f"No .mseed files found in {cache_path}")
        
        # Extract station info from path for debugging
        path_parts = cache_path.parts
        station_info = "unknown"
        if len(path_parts) >= 3:
            station_info = f"{path_parts[-3]}/{path_parts[-2]}/{path_parts[-1]}"
        
        logger.info(f"[DEBUG] Loading {len(mseed_files)} .mseed files from cache for {station_info}...")
        logger.info(f"[DEBUG] Cache path: {cache_path}")
        
        try:
            # Load all files into a single stream
            stream = Stream()
            load_start = time.time()
            files_loaded = 0
            total_size = 0
            
            for i, mseed_file in enumerate(mseed_files):
                try:
                    file_start = time.time()
                    trace_stream = read(str(mseed_file))
                    file_load_time = time.time() - file_start
                    
                    # Calculate file size
                    file_size = mseed_file.stat().st_size if mseed_file.exists() else 0
                    total_size += file_size
                    
                    stream += trace_stream
                    files_loaded += 1
                    
                    # Log every 10th file or if file loading takes > 1 second
                    if (i + 1) % 10 == 0 or file_load_time > 1.0:
                        logger.debug(f"[DEBUG] Loaded file {i+1}/{len(mseed_files)}: {mseed_file.name} "
                                   f"({file_size/1024/1024:.2f} MB, {file_load_time:.2f}s)")
                except Exception as e:
                    logger.warning(f"Failed to parse {mseed_file.name}: {e}")
                    # Skip corrupted files
            
            load_time = time.time() - load_start
            logger.info(f"[DEBUG] File loading complete: {files_loaded}/{len(mseed_files)} files, "
                       f"{total_size/1024/1024:.2f} MB total, {load_time:.2f}s elapsed")
            
            if len(stream) == 0:
                raise ValueError("No valid traces loaded from cache")
            
            # Log trace information before merging
            logger.info(f"[DEBUG] Before merge: {len(stream)} traces")
            total_samples = sum(trace.stats.npts for trace in stream)
            logger.info(f"[DEBUG] Total samples before merge: {total_samples:,}")
            
            # Merge traces when possible (same network, station, location, channel)
            merge_start = time.time()
            logger.info(f"[DEBUG] Starting trace merge operation...")
            stream.merge(method=1)  # Method 1: fill gaps with NaN
            merge_time = time.time() - merge_start
            logger.info(f"[DEBUG] Merge complete: {len(stream)} traces after merge, {merge_time:.2f}s elapsed")
            
            # Log final trace information
            total_samples_after = sum(trace.stats.npts for trace in stream)
            logger.info(f"[DEBUG] Total samples after merge: {total_samples_after:,}")
            for trace in stream:
                logger.debug(f"[DEBUG] Trace: {trace.id}, samples: {trace.stats.npts:,}, "
                           f"rate: {trace.stats.sampling_rate} Hz, "
                           f"duration: {trace.stats.endtime - trace.stats.starttime:.1f}s")
            
            total_time = time.time() - start_time
            logger.info(f"[DEBUG] Loaded stream with {len(stream)} traces in {total_time:.2f}s total")
            return stream
            
        except Exception as e:
            logger.error(f"Failed to load data from cache: {e}", exc_info=True)
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
        logger.info(f"[DEBUG] Starting download of {len(file_urls)} files for {network}/{station}/{year}/{doy:03d}")
        downloaded = self.download_mseed_files(file_urls, cache_path, progress_callback)
        
        if not downloaded:
            raise Exception(f"Failed to download any files from {url}")
        
        logger.info(f"[DEBUG] Download complete: {len(downloaded)}/{len(file_urls)} files cached to {cache_path}")
        return cache_path

