"""
Herramienta para la clasificación e identificación de dispositivos.
Utiliza OUILookup y heurísticas para determinar fabricante y categoría.
"""
import logging
import re
from typing import List, Dict, Optional

from ..utils.oui_lookup import oui_lookup
from ..models.btm_schemas import DeviceInfo, DeviceCategory

logger = logging.getLogger(__name__)

class DeviceClassifier:
    """Clasificador de dispositivos basado en MAC Address."""

    # Keywords para categorización
    MOBILE_VENDORS = ["apple", "samsung", "huawei", "xiaomi", "oppo", "vivo", "oneplus", "google", "motorola", "moto", "lg", "iphone", "ipad"]
    LAPTOP_CHIPS = ["intel", "realtek", "killer", "atheros", "broadcom", "qualcomm"]
    NETWORK_VENDORS = ["cisco", "aruba", "ubiquiti", "tp-link", "netgear", "d-link", "asus", "meraki", "ruckus"]
    VM_VENDORS = ["vmware", "virtual", "qemu", "hyper-v", "parallels"]

    @staticmethod
    def _is_valid_mac(mac_address: str) -> bool:
        """Valida si una cadena es una MAC address válida."""
        if not mac_address or not isinstance(mac_address, str):
            return False
        # Remover separadores comunes (: - .)
        # IMPORTANTE: El guion debe ir al final o escapado para evitar que se interprete como rango
        mac_clean = re.sub(r'[:.\s-]', '', mac_address.lower())
        # Debe tener exactamente 12 caracteres hexadecimales
        return len(mac_clean) == 12 and all(c in '0123456789abcdef' for c in mac_clean)

    def classify_device(
        self, 
        mac_address: str, 
        manual_info: Optional[Dict[str, str]] = None,
        filename: Optional[str] = None
    ) -> DeviceInfo:
        """
        Clasifica un dispositivo singular.
        Si se provee manual_info o filename, se usa para enriquecer.
        """
        # 1. Identificar fabricante por OUI
        vendor = oui_lookup.lookup_vendor(mac_address)
        oui = oui_lookup.get_oui(mac_address)
        
        # Heurística basada en nombre de archivo (Súper útil para el usuario)
        model = None
        if filename:
            # 1. Remover prefijo UUID si existe (f"{uuid}_{name}")
            clean_filename = filename
            if "_" in filename and len(filename.split("_")[0]) >= 32:
                clean_filename = "_".join(filename.split("_")[1:])

            # 2. Limpiar extensión, prefijos numéricos (ej. "15.") y caracteres especiales
            clean_name = re.sub(r'^[0-9]+[\.\s_-]+', '', clean_filename) # Quita "15.", "01 - ", etc
            clean_name = re.sub(r'\.(pcap|pcapng)$', '', clean_name, flags=re.I)
            clean_name = clean_name.replace('_', ' ').replace('-', ' ').strip()
            
            # 3. Intentar extraer marca del nombre del archivo
            for v in self.MOBILE_VENDORS:
                if v in clean_name.lower():
                    if vendor == "Unknown":
                        vendor = v.capitalize()
                    model = clean_name
                    break
            
            if not model and vendor == "Unknown":
                model = clean_name

        # 3. Determinar modelo (si viene manual_info del usuario/API)
        if manual_info:
            if manual_info.get("device_model") or manual_info.get("model"):
                model = manual_info.get("device_model") or manual_info.get("model")
            
            # Override vendor si el usuario lo especifica explícitamente
            if manual_info.get("device_brand"):
                vendor = manual_info.get("device_brand")

        # 4. Categorizar
        category = self._categorize_device(vendor, mac_address)
        
        # 5. Detectar si es virtual/random
        # Validar MAC address antes de parsear
        is_local_admin = False
        if self._is_valid_mac(mac_address):
            try:
                # Remover separadores para obtener solo los caracteres hexadecimales
                # IMPORTANTE: El guion debe ir al final o escapado para evitar que se interprete como rango
                mac_clean = re.sub(r'[:.\s-]', '', mac_address.lower())
                first_octet = int(mac_clean[0:2], 16)
                is_local_admin = (first_octet & 0x02) != 0
            except (ValueError, IndexError) as e:
                logger.warning(f"Error al parsear primer octeto de MAC address '{mac_address}': {e}")
                is_local_admin = False
        
        is_virtual = category == DeviceCategory.VIRTUAL_MACHINE or is_local_admin

        # Calcular confianza
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

    def _categorize_device(self, vendor: str, mac_address: str) -> DeviceCategory:
        """Heurística simple para categorizar dispositivos."""
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
