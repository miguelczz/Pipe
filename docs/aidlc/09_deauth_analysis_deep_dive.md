# 🔍 Análisis Profundo: Manejo del Deauth en Band Steering

## Resumen Ejecutivo

El proyecto NetMind tiene **problemas de precisión críticos** en la detección y validación de paquetes **Deauthentication (Deauth)** y **Disassociation**, que causan que capturas previamente aprobadas sean clasificadas incorrectamente como **FALLIDAS**.

Los problemas radicen en:
1. **Falta de validación de direccionamiento** (DA/SA) en deauth frames
2. **No se filtran deauth dirigidos a otros dispositivos** o broadcast
3. **Codificación de reason codes incorrecta** (se ignoran alguns motivos válidos)
4. **Lógica de ventanas de tiempo muy estricta** (5 segundos para detectar patrón)
5. **Deauth broadcast se cuentan como si fueran dirigidos al cliente**

---

## 📊 Flujo Actual de Deauth (Wireshark Tool)

### 1. Extracción de Deauth (líneas 340-400 de `wireshark_tool.py`)

```python
# Subtype 10 = Disassociation (Management Frame 0x0A)
# Subtype 12 = Deauthentication (Management Frame 0x0C)

if subtype_int == 10:
    event_type = "Disassociation"
elif subtype_int == 12:
    event_type = "Deauthentication"

# Se captura el reason_code
event = {
    "timestamp": float(timestamp),
    "type": event_type,
    "subtype": subtype_int,
    "sa": wlan_sa,      # Source Address (quien envía: AP o cliente)
    "da": wlan_da,      # Destination Address (quién recibe)
    "client_mac": wlan_sa or wlan_da,  # ⚠️ PROBLEMA: Ambiguidad aquí
    "bssid": bssid,
    "reason_code": reason_code,
    # ... más campos
}
```

**Problema #1**: El campo `client_mac` se asigna a `wlan_sa OR wlan_da` sin validar quién es realmente el cliente.

---

### 2. Identificación del Cliente Principal (líneas 431-447)

```python
def is_valid_client_mac(mac: str) -> bool:
    if not mac or mac == "ff:ff:ff:ff:ff:ff" or mac == "00:00:00:00:00:00":
        return False
    first_octet = int(mac.split(':')[0], 16)
    if first_octet & 1: return False  # Ignora multicast
    return True

potential_clients = [m for m in all_client_macs if is_valid_client_mac(m) and m not in bssid_info]
if potential_clients:
    client_mac = Counter(potential_clients).most_common(1)[0][0]
```

**Problema #2**: El cliente se identifica como la MAC **más frecuente** que no esté en BSSIDs. Esto puede fallar si:
- Hay múltiples clientes en la captura (toma el más frecuente)
- El cliente está inactivo la mayor parte de la captura

---

### 3. Procesamiento de Deauth en Steering (líneas 569-580 de `wireshark_tool.py`)

```python
# CASO 1: Steering agresivo (Deauth/Disassoc → Reassoc)
if event_subtype in [10, 12]:  # Disassoc o Deauth
    total_steering_attempts += 1
    
    deauth_time = event["timestamp"]
    deauth_bssid = event["bssid"]
    deauth_band = event["band"]
    reason_code = event["reason_code"]
    
    # Buscar reassociation subsecuente (próximos 15 eventos)
    for j in range(i + 1, min(i + 15, len(client_event_list))):
        next_event = client_event_list[j]
        
        if next_event["subtype"] in [1, 3]:  # Association Response o Reassoc Response
            s_val = int(next_event.get("assoc_status_code", "0"))
            if s_val == 0:
                reassoc_found = True
                # ... registrar transición exitosa
```

**Problema #3**: **NO se valida si el deauth estaba dirigido al cliente identificado**. Un deauth broadcast o dirigido a otro cliente se cuenta como steering válido si hay una reassociation después.

---

### 4. Validación en BTM Analyzer (líneas 380-408 de `btm_analyzer.py`)

```python
# En _run_compliance_checks():

# Análisis de desconexiones (SOLO SI ES EL CLIENTE ANALIZADO)
elif st in [10, 12] and primary_client:
    # Solo penalizar si va dirigido a nuestro cliente
    is_targeted = (e.get("da") == primary_client or e.get("sa") == primary_client)
    # Ignorar motivos de salida voluntaria (3=STA leaving, 8=STA leaving BSS)
    reason = str(e.get("reason_code", "0"))
    is_graceful = reason in ["3", "8"]
    
    if is_targeted and not is_graceful:
        if st == 10: forced_disassoc_count += 1
        else: forced_deauth_count += 1
```

**Aquí hay validación de DA/SA, pero es inconsistente** con la lógica de `wireshark_tool.py`. Además, la lista de "motivos graciosos" es incompleta.

---

## 🎯 Problemas Identificados

### Problema A: Ambiguedad en Direccionamiento (CRÍTICO)

**Situación**: Un deauth/disassoc frame es un **Management Frame** (subtipo 10 o 12) con estructura:
- **SA (Source Address)**: Quién envía (AP en caso de destierro)
- **DA (Destination Address)**: Quién recibe (cliente destituido)
- **BSSID**: El AP que envía

En 802.11, un **Deauth dirigido al cliente** tiene:
- `DA == client_mac` (el cliente recibe el deauth)
- `SA == BSSID` (el AP lo envía)

Un **Deauth broadcast** (enviado a todos) tiene:
- `DA == ff:ff:ff:ff:ff:ff` (broadcast)
- `SA == BSSID`

**Impacto**: Capturas con deauth broadcast se clasifican como "Steering Agresivo" cuando debería ser "Sin Steering Forzado".

---

### Problema B: Reason Codes Incompletos (ALTO)

Actualmente solo se respetan "3" y "8" como motivos graciosos:
- **3**: STA is leaving (client-initiated)
- **8**: Deauthenticated because of inactivity

Pero hay otros razones **que NO indican destierro por steering**:
- **32**: Disassociated due to inactivity
- **33**: Unable to handle another STA
- **34**: Class 2 frame received from nonauthenticated STA
- **35**: Class 3 frame received from nonassociated STA

Y razones **que SÍ indican destierro del AP**:
- **1**: Unspecified reason
- **2**: Previous authentication no longer valid
- **5**: Disassociated because AP is unable to handle all currently associated STAs
- **7**: Class 2 frame received from an unauthenticated STA
- **8**: (ya está)
- **15**: 4-Way Handshake timeout
- **16**: Group Key Handshake timeout
- **17**: IE in 4-Way Handshake differs from (Re)Association Request/Probe Response/Beacon
- **24**: Invalid PMKID
- **25**: Invalid MDE
- **26**: Invalid FTE
- **34**: Disassociated due to poor channel conditions

**Impacto**: Falsos negativos (se culpa al AP por desierro cuando fue por inactividad).

---

### Problema C: Ventana Temporal Muy Estricta (MEDIO)

En `btm_analyzer.py` línea 213:
```python
if last_deauth and (ev["timestamp"] - last_deauth["timestamp"] < 5.0):
    # Es Agresivo (hubo deauth reciente)
```

Esto requiere que la **reassociation ocurra dentro de 5 segundos**. Pero:
- Algunos clientes toman más de 5 segundos para re-asociarse
- Un cliente puede estar buscando otros APs primero (normal)

Debería ser **10-15 segundos** o configurable.

---

### Problema D: Deauth Broadcast Contado como Intento Steering (CRÍTICO)

Un deauth broadcast (DA == ff:ff:ff:ff:ff:ff) se cuenta en:
1. `total_steering_attempts += 1` (línea 570)
2. Se busca reassoc en los siguientes eventos
3. Si hay reassoc exitosa → se marca como "steering agresivo exitoso"

Pero un broadcast **no es un intento de steering dirigido**; podría ser:
- Recarga de AP
- Cambio de configuración
- Pérdida de sincronización

---

### Problema E: Inconsistencia Entre Wireshark y BTM Analyzer (ALTO)

- **wireshark_tool.py**: Cuenta TODO deauth como steering intento, sin validar DA
- **btm_analyzer.py**: Valida DA/SA pero solo penaliza si hay deauth "dirigido"

Esto causa contradicciones en reports:
- Wireshark dice "1 intento, 1 éxito" (cuenta broadcast incorrecto)
- BTM dice "0 deauth forzados" (validación correcta)
- Resultado final: CONFUSIÓN

---

## ✅ Soluciones Propuestas

### Solución 1: Validar Direccionamiento Estricto (CRÍTICO)

**Cambio en `wireshark_tool.py` línea 570:**

```python
# ANTES
if event_subtype in [10, 12]:  # Disassoc o Deauth
    total_steering_attempts += 1
    deauth_time = event["timestamp"]
    deauth_bssid = event["bssid"]
    # ... (buscar reassoc)

# DESPUÉS (PROPUESTO)
if event_subtype in [10, 12]:  # Disassoc o Deauth
    # ✅ VALIDACIÓN CRÍTICA: Solo contar deauth dirigido al cliente
    da = event.get("da", "").lower()
    sa = event.get("sa", "").lower()
    client_check = client_mac.lower() if client_mac else ""
    
    # Ignorar broadcast y multicast
    is_broadcast = da == "ff:ff:ff:ff:ff:ff" or da.startswith("01:00:5e")
    is_directed_to_client = da == client_check  # Cliente recibe el deauth
    
    # Solo contar si está dirigido al cliente ESPECÍFICO
    if is_broadcast:
        logger.info(f"⚠️ Deauth broadcast detectado (ignorado para steering)")
        continue  # Saltar este evento
    
    if not is_directed_to_client:
        logger.info(f"⚠️ Deauth dirigido a {da}, no al cliente {client_check} (ignorado)")
        continue  # Saltar este evento
    
    # Ahora sí, es un deauth dirigido al cliente
    total_steering_attempts += 1
    # ... resto del código
```

---

### Solución 2: Expandir Reason Codes Conocidos (ALTO)

**Crear tabla centralizada** en `backend/src/models/btm_schemas.py` o nuevo archivo:

```python
# Reason codes que INDICAN destierro/steering forzado
FORCED_DEAUTH_REASONS = {
    1: "Unspecified reason (likely AP-initiated)",
    2: "Previous authentication no longer valid",
    5: "Disassociated - AP unable to handle STAs",
    7: "Class 2 frame from unauthenticated STA",
    15: "4-Way Handshake timeout",
    16: "Group Key Handshake timeout",
    17: "IE mismatch in handshake",
    24: "Invalid PMKID",
    25: "Invalid MDE",
    26: "Invalid FTE",
    34: "Disassociated due to poor channel conditions",
}

# Reason codes que NO indican destierro (motivos graceful/normales)
GRACEFUL_DEAUTH_REASONS = {
    3: "STA is leaving (client-initiated)",
    8: "Deauthenticated due to inactivity",
    32: "Disassociated due to inactivity",
    33: "Unable to handle another STA",
    34: "Class 2 frame from nonauthenticated STA",
    35: "Class 3 frame from nonassociated STA",
}

# En BTM Analyzer:
reason_code = int(event.get("reason_code", 0))
is_graceful = reason_code in GRACEFUL_DEAUTH_REASONS
is_forced = reason_code in FORCED_DEAUTH_REASONS or reason_code not in GRACEFUL_DEAUTH_REASONS

if is_directed_to_client and is_forced:
    forced_deauth_count += 1
```

---

### Solución 3: Aumentar Ventana Temporal (MEDIO)

**En `btm_analyzer.py` línea 213:**

```python
# ANTES
REASSOC_TIMEOUT = 5.0

# DESPUÉS (configuración)
REASSOC_TIMEOUT = 15.0  # 15 segundos = más realista

if last_deauth and (ev["timestamp"] - last_deauth["timestamp"] < REASSOC_TIMEOUT):
```

---

### Solución 4: Unificar Lógica Entre Herramientas (CRÍTICO)

**Crear clase compartida `DeauthValidator`** en nuevo módulo `backend/src/utils/deauth_validator.py`:

```python
class DeauthValidator:
    """Valida si un deauth frame es realmente dirigido a un cliente específico"""
    
    @staticmethod
    def is_directed_to_client(deauth_event: Dict, client_mac: str, ap_bssid: str) -> bool:
        """
        Retorna True si el deauth estaba dirigido AL cliente (no es broadcast ni a otros).
        
        Criterios:
        1. DA (Destination) == client_mac (el cliente recibe el deauth)
        2. SA (Source) == ap_bssid O el deauth viene del AP
        3. No es broadcast (DA != ff:ff:ff:ff:ff:ff)
        """
        da = (deauth_event.get("da") or "").lower()
        sa = (deauth_event.get("sa") or "").lower()
        client_check = (client_mac or "").lower()
        ap_check = (ap_bssid or "").lower()
        
        # Rechazar broadcast
        if da == "ff:ff:ff:ff:ff:ff" or da.startswith("01:00:5e"):
            return False
        
        # Debe estar dirigido al cliente
        if da != client_check:
            return False
        
        # Debe venir del AP (o al menos, SA debe ser el BSSID)
        # En algunos casos, SA puede ser el cliente mismo (client-initiated)
        # Pero normalmente en destierro: SA == BSSID
        
        return True
    
    @staticmethod
    def is_forced_deauth(reason_code: int) -> bool:
        """
        Retorna True si el reason_code indica destierro forzado del AP.
        False si es graceful (client-initiated, inactivity, etc).
        """
        # Códigos que son graceful
        graceful = {3, 8, 32, 33, 34, 35}
        
        # Cualquier otro código es considerado forzado (mejor ser conservador)
        return reason_code not in graceful
    
    @staticmethod
    def classify_deauth_event(event: Dict, client_mac: str, ap_bssid: str) -> str:
        """
        Clasifica un deauth en una de:
        - "forced_to_client" (AP destierro al cliente específico)
        - "graceful" (salida normal del cliente)
        - "broadcast" (mensaje general)
        - "directed_to_other" (dirigido a otro cliente)
        """
        if event.get("da") == "ff:ff:ff:ff:ff:ff":
            return "broadcast"
        
        if event.get("da", "").lower() != client_mac.lower():
            return "directed_to_other"
        
        reason = int(event.get("reason_code", 0))
        if DeauthValidator.is_forced_deauth(reason):
            return "forced_to_client"
        else:
            return "graceful"
```

Luego usar en ambas herramientas:
```python
from ..utils.deauth_validator import DeauthValidator

# En wireshark_tool.py
classification = DeauthValidator.classify_deauth_event(event, client_mac, ap_bssid)
if classification == "forced_to_client":
    total_steering_attempts += 1
    # buscar reassoc...
elif classification == "graceful":
    logger.info(f"Deauth graceful (reason {event.get('reason_code')})")
else:
    logger.info(f"Deauth {classification}, ignorado")

# En btm_analyzer.py
if DeauthValidator.is_directed_to_client(event, primary_client, ap_bssid):
    if DeauthValidator.is_forced_deauth(reason_code):
        forced_deauth_count += 1
```

---

## 📋 Checklist de Implementación

- [ ] Crear `backend/src/utils/deauth_validator.py` con clase compartida
- [ ] Actualizar `wireshark_tool.py` para usar validación de direccionamiento
- [ ] Actualizar `btm_analyzer.py` para usar `DeauthValidator` consistentemente
- [ ] Expandir tabla de reason codes en `btm_schemas.py`
- [ ] Aumentar `REASSOC_TIMEOUT` de 5.0 a 15.0 segundos
- [ ] Agregar tests unitarios para deauth_validator.py (casos edge)
- [ ] Validar con capturas previamente "fallidas" (deben pasar ahora)
- [ ] Documentar criterios en README.md del backend
- [ ] Agregar logging detallado para debugging

---

## 🧪 Casos de Prueba Propuestos

### Test 1: Deauth Broadcast Ignorado
```python
def test_deauth_broadcast_ignored():
    """Deauth broadcast (ff:ff:ff:ff:ff:ff) NO debe contar como steering"""
    event = {
        "da": "ff:ff:ff:ff:ff:ff",  # Broadcast
        "sa": "aa:bb:cc:dd:ee:ff",  # AP
        "reason_code": 1,
    }
    assert DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff") == "broadcast"
```

### Test 2: Deauth Dirigido al Cliente
```python
def test_deauth_to_client_counted():
    """Deauth dirigido específicamente al cliente = steering intento"""
    event = {
        "da": "11:22:33:44:55:66",  # Cliente específico
        "sa": "aa:bb:cc:dd:ee:ff",  # AP
        "reason_code": 1,  # Unspecified
    }
    assert DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff") == "forced_to_client"
```

### Test 3: Deauth Graceful (Inactividad)
```python
def test_deauth_graceful_inactivity():
    """Deauth por inactividad (reason 8) = NO es forzado"""
    event = {
        "da": "11:22:33:44:55:66",
        "sa": "aa:bb:cc:dd:ee:ff",
        "reason_code": 8,  # Inactivity
    }
    assert DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff") == "graceful"
```

### Test 4: Deauth a Otro Cliente
```python
def test_deauth_to_other_client():
    """Deauth dirigido a OTRO cliente, no al que analizamos"""
    event = {
        "da": "99:99:99:99:99:99",  # Otro cliente
        "sa": "aa:bb:cc:dd:ee:ff",  # AP
        "reason_code": 1,
    }
    assert DeauthValidator.classify_deauth_event(event, "11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff") == "directed_to_other"
```

---

## 🎓 Referencias IEEE 802.11

- **Deauthentication Frame (0x0C)**: Management frame que termina autenticación
- **Disassociation Frame (0x0A)**: Management frame que termina asociación
- **Reason Code**: 2 bytes que indican motivo; registrados en IEEE 802.11-2016
- **Directed vs Broadcast**: DA field determina si es unicast o broadcast

---

## 📌 Notas de Implementación

1. **Mantener compatibilidad hacia atrás**: Las capturas correctamente procesadas no deben cambiar
2. **Logging extenso**: Cada deauth debe logearse con su clasificación para debugging
3. **Configuración**: Considera hacer `REASSOC_TIMEOUT` configurable en `settings.py`
4. **Performance**: La validación es O(1), sin impacto en rendimiento
5. **Validación de entrada**: Normalizar MACs a formato lowercase para comparaciones

---

**Autor**: Análisis automatizado del ciclo AIDLC  
**Fecha**: 2026-01-26  
**Criticidad**: 🔴 ALTA (afecta correctness de resultados principales)
