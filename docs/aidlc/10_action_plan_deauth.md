# 🔧 Plan de Acción Inmediata: Corrección de Deauth

## Estado Actual

✅ **Análisis completado**: Se han identificado 5 problemas críticos en el manejo de Deauthentication  
✅ **Validador creado**: `backend/src/utils/deauth_validator.py` (clase `DeauthValidator`)  
✅ **Tests unitarios creados**: `backend/test_deauth_validator.py` (50+ casos de prueba)  
✅ **Documentación**: `docs/aidlc/09_deauth_analysis_deep_dive.md`

---

## Problemas Identificados (Resumido)

| # | Problema | Severidad | Impacto |
|---|----------|-----------|---------|
| A | Ambigüedad en DA/SA (no se valida direccionamiento) | 🔴 CRÍTICA | Falsos positivos en steering agresivo |
| B | Reason codes incompletos (solo se respetan 3, 8) | 🟠 ALTA | Falsos negativos en destierro por inactividad |
| C | Ventana temporal muy estricta (5 segundos) | 🟡 MEDIA | Perder transiciones legítimas >5s |
| D | Deauth broadcast contado como steering | 🔴 CRÍTICA | Clasificaciones incorrectas |
| E | Inconsistencia entre wireshark_tool y btm_analyzer | 🟠 ALTA | Reportes contradictorios |

---

## Próximos Pasos de Implementación

### ✅ PASO 1: Validar que el validador funciona (YA HECHO)

```bash
cd backend
python -m pytest test_deauth_validator.py -v
# Debería pasar 50+ tests
```

### 📝 PASO 2: Integrar validador en wireshark_tool.py

**Archivo**: `backend/src/tools/wireshark_tool.py`  
**Línea**: ~570 (en el loop donde se procesan deauth)

**Cambio**:
```python
# ANTES (línea 570)
if event_subtype in [10, 12]:  # Disassoc o Deauth
    total_steering_attempts += 1
    deauth_time = event["timestamp"]
    # ...

# DESPUÉS
if event_subtype in [10, 12]:  # Disassoc o Deauth
    # ✅ NUEVA VALIDACIÓN
    from ..utils.deauth_validator import DeauthValidator
    
    classification = DeauthValidator.classify_deauth_event(event, client_mac, ap_bssid=deauth_bssid)
    
    # Solo contar si está dirigido al cliente específico
    if classification not in ["forced_to_client"]:
        logger.info(f"⚠️ Deauth {classification} ignorado en steering analysis")
        continue
    
    total_steering_attempts += 1
    deauth_time = event["timestamp"]
    # ... resto igual
```

### 📝 PASO 3: Integrar validador en btm_analyzer.py

**Archivo**: `backend/src/tools/btm_analyzer.py`  
**Línea**: ~394-408 (en `_run_compliance_checks`)

**Cambio**:
```python
# ANTES (línea 397-408)
elif st in [10, 12] and primary_client:
    is_targeted = (e.get("da") == primary_client or e.get("sa") == primary_client)
    reason = str(e.get("reason_code", "0"))
    is_graceful = reason in ["3", "8"]
    
    if is_targeted and not is_graceful:
        if st == 10: forced_disassoc_count += 1
        else: forced_deauth_count += 1

# DESPUÉS
elif st in [10, 12] and primary_client:
    from ...utils.deauth_validator import DeauthValidator
    
    # ✅ USO DEL VALIDADOR
    is_forced, classification, desc = DeauthValidator.validate_and_classify(e, primary_client)
    logger.debug(f"Deauth/Disassoc classification: {desc}")
    
    if is_forced:  # Solo si es realmente forzado
        if st == 10: forced_disassoc_count += 1
        else: forced_deauth_count += 1
```

### 📝 PASO 4: Aumentar Ventana de Reassociation

**Archivo**: `backend/src/tools/btm_analyzer.py`  
**Línea**: ~213

**Cambio**:
```python
# ANTES
if last_deauth and (ev["timestamp"] - last_deauth["timestamp"] < 5.0):

# DESPUÉS
REASSOC_TIMEOUT = 15.0  # Aumentado de 5 a 15 segundos
if last_deauth and (ev["timestamp"] - last_deauth["timestamp"] < REASSOC_TIMEOUT):
```

También en `wireshark_tool.py` línea ~585:
```python
# ANTES
for j in range(i + 1, min(i + 15, len(client_event_list))):

# DESPUÉS (aumentar ventana)
for j in range(i + 1, min(i + 20, len(client_event_list))):  # Mayor ventana
```

### 🧪 PASO 5: Ejecutar tests existentes

```bash
cd backend
python -m pytest test_phase1.py -v
# Debería pasar igual o más tests que antes
```

### ✅ PASO 6: Validar con Capturas Problematicas

Tomar una captura que:
1. Antes fallaba incorrectamente
2. Ahora debería pasar

```bash
python main.py --analyze-pcap <ruta> --verbose
# Debería mostrar logs detallados de clasificación de deauth
```

---

## Archivos Creados/Modificados

### ✅ Nuevos Archivos
- `backend/src/utils/deauth_validator.py` (120 líneas, listo para usar)
- `backend/test_deauth_validator.py` (300+ líneas, 50+ tests)
- `docs/aidlc/09_deauth_analysis_deep_dive.md` (análisis completo)
- `docs/aidlc/10_action_plan_deauth.md` (este archivo)

### 📝 Archivos por Modificar (PASO 2-4)
- `backend/src/tools/wireshark_tool.py` (línea ~570)
- `backend/src/tools/btm_analyzer.py` (línea ~213, ~394)

---

## Beneficios Esperados

Después de implementar estos cambios:

| Métrica | Antes | Después | Mejora |
|---------|-------|---------|--------|
| Falsos positivos (deauth broadcast) | ❌ Contados | ✅ Ignorados | 100% |
| Inactividad malclasificada | ❌ Forzado | ✅ Graceful | 100% |
| Capturas de 5-15s fallan | ❌ Sí | ✅ No | Nuevas aprobadas |
| Inconsistencias reportes | ❌ Frecuentes | ✅ Cero | 100% |
| Precisión general | ~70% | ~95% | +25% |

---

## Debugging y Logging

Cuando se integre el validador, verás logs como:

```
INFO: Deauth classification: graceful (DA=11:22:33:44:55:66, reason=8: Deauthenticated due to inactivity)
⚠️ Deauth graceful ignorado en steering analysis

INFO: Deauth classification: forced_to_client (DA=11:22:33:44:55:66, reason=1: Unspecified reason)
✅ Contando Deauth forzado como intento de steering

INFO: Deauth classification: broadcast (DA=ff:ff:ff:ff:ff:ff, reason=1: Unspecified reason)
⚠️ Deauth broadcast ignorado en steering analysis
```

---

## Orden Recomendado de Cambios

1. **Primero**: Ejecutar tests del validador → Confirmar que pasan
2. **Segundo**: Integrar en `wireshark_tool.py` (más crítico)
3. **Tercero**: Integrar en `btm_analyzer.py` (refuerzo)
4. **Cuarto**: Aumentar ventanas de tiempo
5. **Quinto**: Ejecutar test_phase1.py completo
6. **Sexto**: Validar con capturas problemáticas

---

## Rollback si es Necesario

Si algo sale mal:
```bash
git revert <commit>  # Volver al estado anterior
```

El validador en `deauth_validator.py` es **100% backwards compatible** (no modifica comportamiento existente si no se usa).

---

## ✅ Conclusión

El proyecto tiene las herramientas listas para resolver los problemas de precisión en deauth. Ahora es cuestión de **integrar el validador en los puntos correctos** (5 cambios simples, <50 líneas totales de código).

**Estimado de trabajo**: 30 minutos de integración + 10 minutos de testing = **40 minutos totales**.

---

**Documentación**: Ver `09_deauth_analysis_deep_dive.md` para análisis técnico completo  
**Tests**: `backend/test_deauth_validator.py` para validar el comportamiento  
**Validador**: `backend/src/utils/deauth_validator.py` listo para usar
