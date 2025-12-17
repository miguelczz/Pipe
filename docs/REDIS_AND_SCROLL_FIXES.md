# Correcciones Críticas: Scroll y Persistencia Redis

## 1. 📱 Bloqueo de UI (Scroll "Saltarín")

**Problema:**
Durante el streaming, el chat forzaba el scroll hacia abajo en cada token (20 veces por segundo), impidiendo al usuario subir para leer mensajes anteriores o el principio de la respuesta.

**Solución:**
Se implementó "Smart Auto-Scroll" en `frontend/src/components/chat/ChatContainer.jsx`.
- **Antes:** Scroll forzado siempre que cambian los mensajes.
- **Ahora:** Solo hace scroll si el usuario ya está visualmente al final del chat (<100px). Si el usuario sube, el scroll automático se desactiva hasta que vuelva a bajar.

## 2. 💾 Contexto Perdido en Producción (Redis)

**Problema:**
En entorno local funcionaba parcialmente, pero en producción el contexto se perdía.
La causa raíz era que `session_state.add_message(...)` solo actualizaba el objeto en la memoria RAM del contenedor.
El `RedisSessionManager` nunca recibía la orden de escribir esos cambios en la base de datos Redis.

**Solución:**
Se añadieron llamadas explícitas a `session_manager.update_session(...)` en `backend/src/api/streaming.py`:
1.  Inmediatamente después de guardar el mensaje del usuario.
2.  Al finalizar el streaming, después de guardar la respuesta completa del asistente.

Esto garantiza que el estado se serialice y se guarde en Redis, asegurando que:
- El contexto persista entre peticiones.
- Funcione correctamente en entornos con múltiples réplicas del backend.
- Sobreviva a reinicios del contenedor.

## 🧪 Verificación

1.  **Scroll:** Envía una pregunta larga. Mientras responde, intenta subir (scroll up). Deberías poder quedarte ahí sin que te baje a la fuerza.
2.  **Contexto:**
    - Envía: "Mi nombre es Miguel".
    - Reinicia el backend (simulando despliegue).
    - Envía: "¿Cómo me llamo?".
    - Debería responder correctamente gracias a Redis.
