# 📋 AIDLC - Fase 1: Inception y Requerimientos

## 🎯 Visión del Proyecto

### Objetivo Principal
Implementar un sistema inteligente de análisis de Band Steering que automatice la evaluación de pruebas Wireshark, genere reportes de cumplimiento y organice resultados por marca de dispositivo, siguiendo el ciclo de vida de IA (AIDLC).

### Problema a Resolver
Actualmente, el análisis de pruebas Band Steering es:
- **Manual y tedioso**: Requiere expertise técnico para interpretar capturas
- **Inconsistente**: Diferentes analistas pueden llegar a conclusiones distintas
- **No escalable**: No hay forma eficiente de comparar dispositivos o marcas
- **Sin trazabilidad**: Falta de documentación estructurada de resultados

### Solución Propuesta
Sistema automatizado que:
1. **Analiza automáticamente** capturas Wireshark para Band Steering
2. **Clasifica códigos BTM** según situaciones específicas (éxito/fallo)
3. **Genera tablas de cumplimiento** con métricas KVR (802.11k/v/r)
4. **Extrae fragmentos relevantes** de cambios de canal
5. **Organiza por marcas** de dispositivos automáticamente
6. **Mejora el chat RAG** para consultas técnicas especializadas

## 📊 Stakeholders y Usuarios

### Usuarios Primarios
- **Ingenieros de RF**: Análisis técnico de comportamiento de dispositivos
- **QA Testers**: Validación de cumplimiento de estándares
- **Arquitectos de Red**: Evaluación de rendimiento por marca

### Usuarios Secundarios
- **Gerentes Técnicos**: Reportes ejecutivos de cumplimiento
- **Soporte Técnico**: Consultas sobre problemas específicos
- **Desarrolladores**: Integración con otros sistemas

## 🎯 Requerimientos Funcionales

### RF-001: Análisis Automático de BTM
**Como** ingeniero de RF  
**Quiero** que el sistema analice automáticamente códigos BTM en capturas  
**Para** identificar patrones de éxito y fallo sin análisis manual

**Criterios de Aceptación:**
- Detectar códigos BTM estándar (0-8) según 802.11v
- Clasificar automáticamente como éxito/fallo/parcial
- Identificar patrones de steering agresivo vs asistido
- Calcular métricas de tiempo de transición

### RF-002: Tabla de Cumplimiento KVR
**Como** QA tester  
**Quiero** una tabla automática de cumplimiento de estándares  
**Para** validar soporte de 802.11k/v/r en dispositivos

**Criterios de Aceptación:**
- Evaluar soporte de 802.11k (Radio Measurement)
- Evaluar soporte de 802.11v (BSS Transition Management)
- Evaluar soporte de 802.11r (Fast Transition)
- Generar score de cumplimiento (0-100%)
- Incluir recomendaciones específicas

### RF-003: Extracción de Fragmentos
**Como** ingeniero de RF  
**Quiero** ver fragmentos específicos de cambios de canal  
**Para** analizar visualmente las transiciones críticas

**Criterios de Aceptación:**
- Extraer secuencias de cambio de canal
- Mostrar timeline de eventos BTM
- Filtrar paquetes relevantes automáticamente
- Exportar fragmentos en formato pcap

### RF-004: Organización por Marcas
**Como** arquitecto de red  
**Quiero** que los resultados se organicen por marca de dispositivo  
**Para** comparar comportamiento entre fabricantes

**Criterios de Aceptación:**
- Detectar marca automáticamente por OUI
- Crear carpetas por marca (Samsung, Apple, etc.)
- Generar estadísticas comparativas
- Identificar patrones específicos por marca

### RF-005: Chat RAG Especializado
**Como** usuario técnico  
**Quiero** hacer consultas específicas sobre análisis  
**Para** obtener explicaciones detalladas de resultados

**Criterios de Aceptación:**
- Consultar sobre códigos BTM específicos
- Explicar fallos detectados
- Recomendar soluciones basadas en análisis
- Acceder a documentación técnica contextual

## 🎯 Requerimientos No Funcionales

### RNF-001: Rendimiento
- Análisis de capturas <2MB en <30 segundos
- Análisis de capturas <10MB en <2 minutos
- Respuesta de chat RAG en <5 segundos

### RNF-002: Precisión
- Detección de códigos BTM: >95% precisión
- Clasificación de éxito/fallo: >90% precisión
- Identificación de marcas: >98% precisión

### RNF-003: Escalabilidad
- Soportar análisis de hasta 100 capturas simultáneas
- Base de datos para >10,000 análisis históricos
- Comparación entre hasta 50 marcas diferentes

### RNF-004: Usabilidad
- Interfaz intuitiva para usuarios no técnicos
- Reportes exportables en PDF/HTML
- Documentación integrada y contextual

## 📈 Métricas de Éxito

### Métricas Técnicas
- **Tiempo de análisis**: Reducción del 80% vs análisis manual
- **Precisión de detección**: >95% en códigos BTM
- **Cobertura de estándares**: 100% de KVR evaluado
- **Automatización**: 90% de tareas sin intervención manual

### Métricas de Negocio
- **Productividad**: 5x más análisis por día
- **Consistencia**: 95% de concordancia entre análisis
- **Trazabilidad**: 100% de análisis documentados
- **Satisfacción**: >4.5/5 en encuestas de usuario

## 🚧 Restricciones y Limitaciones

### Técnicas
- Dependencia de tshark para análisis de capturas
- Limitado a capturas en formato pcap/pcapng
- Requiere conectividad para lookup de OUI
- Análisis limitado a estándares 802.11k/v/r

### Operacionales
- Requiere conocimiento básico de redes Wi-Fi
- Capturas deben contener tráfico de management frames
- Análisis óptimo requiere capturas >30 segundos
- Limitado a dispositivos con MAC addresses válidas

## 🔄 Casos de Uso Principales

### CU-001: Análisis de Captura Nueva
1. Usuario sube archivo de captura
2. Sistema detecta automáticamente dispositivos
3. Analiza códigos BTM y transiciones
4. Genera reporte de cumplimiento
5. Organiza en carpeta por marca
6. Notifica resultados al usuario

### CU-002: Comparación entre Marcas
1. Usuario selecciona múltiples análisis
2. Sistema agrupa por marca de dispositivo
3. Calcula estadísticas comparativas
4. Genera reporte de benchmarking
5. Identifica mejores/peores performers

### CU-003: Consulta Técnica Especializada
1. Usuario hace pregunta sobre análisis
2. Sistema busca en documentación técnica
3. Contextualiza con resultados específicos
4. Proporciona explicación detallada
5. Sugiere acciones correctivas

## 📋 Backlog Inicial

### Epic 1: Análisis BTM Inteligente
- Historia: Detección automática de códigos BTM
- Historia: Clasificación de patrones de steering
- Historia: Cálculo de métricas de rendimiento
- Historia: Validación de transiciones exitosas

### Epic 2: Sistema de Cumplimiento
- Historia: Evaluación de soporte KVR
- Historia: Generación de tabla de cumplimiento
- Historia: Cálculo de scores automáticos
- Historia: Recomendaciones personalizadas

### Epic 3: Gestión por Marcas
- Historia: Detección automática de fabricantes
- Historia: Organización en carpetas por marca
- Historia: Estadísticas comparativas
- Historia: Identificación de patrones específicos

### Epic 4: Mejoras de RAG
- Historia: Indexación de documentos técnicos
- Historia: Consultas especializadas en BTM
- Historia: Explicación de fallos detectados
- Historia: Recomendaciones contextuales

## 🎯 Definición de "Terminado" (DoD)

Para cada funcionalidad:
- [ ] Código implementado y testeado
- [ ] Documentación técnica actualizada
- [ ] Casos de prueba automatizados
- [ ] Validación con usuarios reales
- [ ] Métricas de rendimiento verificadas
- [ ] Integración con sistema existente
- [ ] Documentación de usuario actualizada

---

**Próximo paso**: Proceder a la fase de Diseño Arquitectónico