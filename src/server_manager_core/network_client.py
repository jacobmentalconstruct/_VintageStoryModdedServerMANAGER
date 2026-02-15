import urllib.request
import urllib.error
import json
from typing import Optional, Dict, Any

class NetworkClient:
    API_BASE = "http://mods.vintagestory.at/api"

    def __init__(self, log_fn):
        self.log = log_fn

    def fetch_mod_db(self) -> Optional[Dict[str, Any]]:
        """
        Fetches the entire mod list from Vintage Story ModDB.
        Returns the parsed JSON or None on failure.
        """
        url = f"{self.API_BASE}/mods"
        try:
            self.log(f"[NET] Fetching catalog from {url}...")
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    self.log("[NET] Catalog fetch successful.")
                    return data
        except Exception as e:
            self.log(f"[NET-ERR] Failed to fetch ModDB: {e}")
            return None

    def download_file(self, url: str, dest_path: str) -> bool:
        """
        Streams a file download to the destination path.
        """
        try:
            self.log(f"[NET] Downloading: {url}")
            # User-Agent is sometimes required by strict servers, though VS ModDB is usually lenient.
            req = urllib.request.Request(
                url, 
                data=None, 
                headers={'User-Agent': 'VS-Server-Manager/1.0'}
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                with open(dest_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            self.log(f"[NET] Saved to: {dest_path}")
            return True
        except Exception as e:
            self.log(f"[NET-ERR] Download failed: {e}")
            return False