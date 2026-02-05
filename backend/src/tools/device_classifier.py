"""
Herramienta para la clasificación e identificación de dispositivos.
Utiliza OUILookup y heurísticas para determinar fabricante y categoría,
sin responsabilidades de logging.
"""
import re
from typing import List, Dict, Optional

from ..utils.oui_lookup import oui_lookup
from ..models.btm_schemas import DeviceInfo, DeviceCategory

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
        
        # 2. Heurística basada en nombre de archivo (Súper útil para el usuario)
        model = None
        if filename:
            vendor, model = self._infer_from_filename(
                filename=filename,
                current_vendor=vendor,
            )
        
        # 3. Enriquecer con información manual (usuario/API)
        vendor, model = self._enrich_with_manual_info(
            manual_info=manual_info,
            current_vendor=vendor,
            current_model=model,
        )

        # 4. Categorizar
        category = self._categorize_device(vendor, mac_address)
        
        # 5. Detectar si es virtual/random
        is_local_admin = self._is_local_admin_mac(mac_address)
        
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

    def _infer_from_filename(
        self,
        filename: str,
        current_vendor: str,
    ) -> (str, Optional[str]):
        """
        Extrae pistas de vendor/model a partir del nombre del archivo de captura.
        
        - Limpia UUIDs y prefijos numéricos.
        - Intenta mapear marcas móviles conocidas.
        - Si el vendor es Unknown, usa el nombre limpio como modelo.
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
        Aplica información manual del usuario/API sobre vendor/model.
        
        - Permite override explícito de marca.
        - Usa campos comunes como `device_model` o `model`.
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
        Detecta si una MAC tiene el bit de administración local (random/virtual).
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
