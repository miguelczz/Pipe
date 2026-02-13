"""
Tool for classification and identification of devices.
Uses OUILookup and heuristics to determine vendor and category,
without logging responsibilities.
"""
import re
from typing import List, Dict, Optional

from ..utils.oui_lookup import oui_lookup
from ..models.btm_schemas import DeviceInfo, DeviceCategory

class DeviceClassifier:
    """Device classifier based on MAC Address."""

    # Categorization keywords
    MOBILE_VENDORS = ["apple", "samsung", "huawei", "xiaomi", "oppo", "vivo", "oneplus", "google", "motorola", "moto", "lg", "iphone", "ipad"]
    LAPTOP_CHIPS = ["intel", "realtek", "killer", "atheros", "broadcom", "qualcomm"]
    NETWORK_VENDORS = ["cisco", "aruba", "ubiquiti", "tp-link", "netgear", "d-link", "asus", "meraki", "ruckus"]
    VM_VENDORS = ["vmware", "virtual", "qemu", "hyper-v", "parallels"]

    @staticmethod
    def _is_valid_mac(mac_address: str) -> bool:
        """Validates if a string is a valid MAC address."""
        if not mac_address or not isinstance(mac_address, str):
            return False
        # Remove common separators (: - .)
        # IMPORTANT: The hyphen must go at the end or escaped to avoid range interpretation
        mac_clean = re.sub(r'[:.\s-]', '', mac_address.lower())
        # Must have exactly 12 hexadecimal characters
        return len(mac_clean) == 12 and all(c in '0123456789abcdef' for c in mac_clean)

    def classify_device(
        self, 
        mac_address: str, 
        manual_info: Optional[Dict[str, str]] = None,
        filename: Optional[str] = None
    ) -> DeviceInfo:
        """
        Classifies a single device.
        If manual_info or filename is provided, it is used for enrichment.
        """
        # 1. Identify vendor by OUI
        vendor = oui_lookup.lookup_vendor(mac_address)
        oui = oui_lookup.get_oui(mac_address)
        
        # 2. Heuristic based on filename (super useful for the user)
        model = None
        if filename:
            vendor, model = self._infer_from_filename(
                filename=filename,
                current_vendor=vendor,
            )
        
        # 3. Enrich with manual information (user/API)
        vendor, model = self._enrich_with_manual_info(
            manual_info=manual_info,
            current_vendor=vendor,
            current_model=model,
        )
 
        # 4. Categorize
        category = self._categorize_device(vendor, mac_address)
        
        # 5. Detect if virtual/random
        is_local_admin = self._is_local_admin_mac(mac_address)
        
        is_virtual = category == DeviceCategory.VIRTUAL_MACHINE or is_local_admin
 
        # Calculate confidence
        confidence = 0.9 if vendor != "Unknown" else 0.1
        if manual_info or (filename and vendor != "Unknown"): 
            confidence = 1.0

        return DeviceInfo(
            mac_address=mac_address,
            oui=oui,
            vendor=vendor,
            device_model=model,
            device_category=category,
            is_virtual=is_virtual,
            confidence_score=confidence
        )

    def _infer_from_filename(
        self,
        filename: str,
        current_vendor: str,
    ) -> (str, Optional[str]):
        """
        Extracts vendor/model hints from the capture filename.
        
        - Cleans UUIDs and numerical prefixes.
        - Tries to map known mobile brands.
        - If vendor is Unknown, uses the clean name as model.
        """
        vendor = current_vendor
        model = None

        clean_filename = filename
        if "_" in filename and len(filename.split("_")[0]) >= 32:
            clean_filename = "_".join(filename.split("_")[1:])

        clean_name = re.sub(r'^[0-9]+[\.\s_-]+', '', clean_filename)
        clean_name = re.sub(r'\.(pcap|pcapng)$', '', clean_name, flags=re.I)
        clean_name = clean_name.replace("_", " ").replace("-", " ").strip()

        lower_name = clean_name.lower()
        for v in self.MOBILE_VENDORS:
            if v in lower_name:
                if vendor == "Unknown":
                    vendor = v.capitalize()
                model = clean_name
                break

        if not model and vendor == "Unknown":
            model = clean_name

        return vendor, model

    def _enrich_with_manual_info(
        self,
        manual_info: Optional[Dict[str, str]],
        current_vendor: str,
        current_model: Optional[str],
    ) -> (str, Optional[str]):
        """
        Applies manual information from user/API on vendor/model.
        
        - Allows explicit brand override.
        - Uses common fields like `device_model` or `model`.
        """
        vendor = current_vendor
        model = current_model

        if not manual_info:
            return vendor, model

        if manual_info.get("device_model") or manual_info.get("model"):
            model = manual_info.get("device_model") or manual_info.get("model")

        if manual_info.get("device_brand"):
            vendor = manual_info.get("device_brand")

        return vendor, model

    def _is_local_admin_mac(self, mac_address: str) -> bool:
        """
        Detects if a MAC has the local administration bit (random/virtual).
        """
        if not self._is_valid_mac(mac_address):
            return False
        try:
            mac_clean = re.sub(r'[:.\s-]', '', mac_address.lower())
            first_octet = int(mac_clean[0:2], 16)
            return (first_octet & 0x02) != 0
        except (ValueError, IndexError):
            return False

    def _categorize_device(self, vendor: str, mac_address: str) -> DeviceCategory:
        """Simple heuristic to categorize devices."""
        v_lower = vendor.lower()
        
        if any(x in v_lower for x in self.VM_VENDORS):
            return DeviceCategory.VIRTUAL_MACHINE
            
        if any(x in v_lower for x in self.MOBILE_VENDORS):
            return DeviceCategory.MOBILE
            
        if any(x in v_lower for x in self.LAPTOP_CHIPS):
            return DeviceCategory.COMPUTER
            
        if any(x in v_lower for x in self.NETWORK_VENDORS):
            return DeviceCategory.NETWORK_EQUIPMENT
            
        return DeviceCategory.UNKNOWN
