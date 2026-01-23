
# Cambios realizados en este turno:
- Backend (wireshark_tool.py): 
    - Se agregaron campos redundantes para btm_status_code aprovechando tanto wlan.fixed como wlan.wnm.
    - Se implementó lógica para identificar la MAC del cliente (la más frecuente que no sea un BSSID).
    - Se incluyó la client_mac en el objeto de diagnóstico.
- Frontend (NetworkAnalysisPage.jsx):
    - Se rediseñó la tarjeta de BSSIDs para mostrar "MACs de Negociación".
    - Ahora muestra la MAC del cliente y la lista de BSSIDs involucrados.
- Backend (btm_analyzer.py):
    - Se aseguró que los códigos de estado aparezcan incluso en caso de fallo (0 responses) si fueron capturados en otros frames WNM.
