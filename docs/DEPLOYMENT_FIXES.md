# Solución de Problemas de Streaming en Producción

Si en tu entorno local (desarrollo) el streaming funciona correctamente, pero en el despliegue (producción) la respuesta llega "de golpe" al final, el problema es **Buffering** en el servidor web o balanceador de carga.

## 🔍 Causa Raíz

Server-Sent Events (SSE) envía datos en pequeños "paquetes" o chunks.
- **Sin buffering:** El servidor envía "Hola", el cliente recibe "Hola". (Correcto)
- **Con buffering (Nginx/Cloud default):** El servidor envía "Hola". El proxy (Nginx) dice "Es muy poco datos, voy a esperar a llenar 4KB". El servidor envía más texto. Nginx sigue esperando. Al final, el servidor cierra la conexión. Nginx dice "Ya terminó, envío todo junto". El cliente recibe todo de golpe. (Incorrecto para streaming)

## 🛠️ Soluciones

### 1. Configuración de Nginx (Reverso Proxy)

Si usas Nginx delante de tu contenedor Docker, añade estas líneas en tu bloque `location /`:

```nginx
location / {
    proxy_pass http://backend:8000;
    
    # 🔴 CRÍTICO: Desactivar buffering para streaming
    proxy_buffering off;
    
    # Headers necesarios para SSE
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
    
    # Headers estándar
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Aunque el backend ya envía el header `X-Accel-Buffering: no`, a veces es necesario forzar `proxy_buffering off;` explícitamente en la configuración.

### 2. Configuración de Traefik (si lo usas)

Si usas Traefik como Ingress o Proxy, añade etiquetas para desactivar el buffering:

```yaml
labels:
  - "traefik.http.middlewares.no-compress.compress=false"
  - "traefik.http.middlewares.no-buffer.buffering.maxRequestBodyBytes=0"
```

### 3. Cloudflare (CDN)

Si tu dominio pasa por Cloudflare:
1.  Ve a **Caching** > **Configuration**.
2.  Desactiva **Proxying** para el subdominio del API (nube gris en DNS).
3.  O crea una **Page Rule** para `/agent/query/stream` con:
    *   Cache Level: Bypass
    *   Rocket Loader: Off

### 4. AWS Application Load Balancer (ALB)

Los ALBs de AWS no soportan SSE de forma nativa si no se configuran correctamente:
*   Asegúrate de usar **HTTP/2** si es posible.
*   Aumenta el **Idle Timeout** (el streaming puede tener pausas).

## ✅ Verificación

Para confirmar que el problema es buffering:
1.  Abre las **DevTools** del navegador (F12).
2.  Ve a la pestaña **Network**.
3.  Filtra por `/stream`.
4.  Si ves que la petición se queda "Pending" por varios segundos y luego completa de golpe con status 200, es buffering.
5.  Si funcionara bien, verías status 200 inmediatamente y datos llegando poco a poco.
