"""
Utility service for vendor lookup by OUI (MAC Address).
Supports local cache and a static database of common vendors.
Does not perform logging; only resolves vendors deterministically.
"""
import re
from typing import Optional, Dict

class OUILookup:
    """
    Identifies the vendor of a device based on its MAC Address.
    """
    
    # Static database of common OUIs (Simplified for MVP)
    # In production, this could load a CSV file or query an API.
    KNOWN_OUIS = {
        # Apple
        "00:17:f2": "Apple", "00:1b:63": "Apple", "00:1c:b3": "Apple", "00:1e:52": "Apple", "00:1f:5b": "Apple", 
        "00:1f:f3": "Apple", "00:21:e9": "Apple", "00:22:41": "Apple", "00:23:12": "Apple", "00:23:32": "Apple",
        "00:23:6c": "Apple", "00:23:df": "Apple", "00:24:36": "Apple", "00:25:00": "Apple", "00:25:4b": "Apple",
        "00:25:bc": "Apple", "00:26:08": "Apple", "00:26:4a": "Apple", "00:26:b0": "Apple", "00:26:bb": "Apple",
        
        # Samsung
        "00:02:78": "Samsung", "00:07:ab": "Samsung", "00:09:18": "Samsung", "00:0d:ae": "Samsung",
        "00:12:47": "Samsung", "00:12:fb": "Samsung", "00:13:77": "Samsung", "00:15:99": "Samsung",
        "00:15:b9": "Samsung", "00:16:32": "Samsung", "00:16:6b": "Samsung", "00:16:db": "Samsung",
        
        # Huawei
        "00:18:82": "Huawei", "00:19:e0": "Huawei", "00:1e:10": "Huawei", "00:25:68": "Huawei",
        "00:46:4b": "Huawei", "00:66:4b": "Huawei", "00:e0:fc": "Huawei",
        
        # Intel (Common chips in laptops)
        "00:13:e8": "Intel", "00:1b:21": "Intel", "00:21:6a": "Intel", "00:22:fb": "Intel",
        
        # Random / Virtual
        "02:00:00": "Virtual", "06:00:00": "Virtual"
    }
    
    _cache: Dict[str, str] = {}

    def lookup_vendor(self, mac_address: str) -> str:
        """
        Returns the vendor name for a given MAC.
        Returns 'Unknown' if not found.
        """
        if not mac_address:
            return "Unknown"
        
        # Normalize MAC
        normalized_mac = mac_address.lower().replace("-", ":")
        
        # Extract OUI (first 3 octets: xx:xx:xx)
        # Basic format validation
        match = re.match(r'^([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', normalized_mac)
        if not match:
            return "Unknown"
            
        oui = match.group(1)
        
        # Check cache
        if oui in self._cache:
            return self._cache[oui]
        
        # Check internal DB
        vendor = self.KNOWN_OUIS.get(oui)
        
        if not vendor:
            # Attempt for "fuzzy" lookup or external API would go here
            # For now return Unknown
            vendor = "Unknown"
        
        # Save in cache
        self._cache[oui] = vendor
        return vendor

    def get_oui(self, mac_address: str) -> str:
        """Extracts the OUI from a MAC."""
        normalized_mac = mac_address.lower().replace("-", ":")
        match = re.match(r'^([0-9a-f]{2}:[0-9a-f]{2}:[0-9a-f]{2})', normalized_mac)
        return match.group(1) if match else "00:00:00"

# Singleton instance for easy use
oui_lookup = OUILookup()
