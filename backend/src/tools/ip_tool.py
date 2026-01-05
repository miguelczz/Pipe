import re
import subprocess
import ipaddress
import platform
import socket
import time
from typing import Dict, Any, Optional
from ..core.cache import cache_result

# Intentar importar ping3 como alternativa cuando subprocess no funciona
try:
    import ping3
    PING3_AVAILABLE = True
except ImportError:
    PING3_AVAILABLE = False


class IPTool:
    def validate_ip(self, ip: str) -> bool:
        """
        Valida si el string es una dirección IPv4.
        """
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

    def validate_ip_or_domain(self, host: str) -> bool:
        """
        Valida si el string es una IP o un dominio válido.
        """
        # IPv4 simple
        ip_pattern = r"^(?:\d{1,3}\.){3}\d{1,3}$"
        # Dominio básico (subdominios y TLD)
        domain_pattern = r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$"
        return bool(re.match(ip_pattern, host) or re.match(domain_pattern, host))

    def resolve_domain(self, host: str) -> str:
        """
        Resuelve un dominio a su dirección IP.
        Si ya es una IP, la devuelve tal cual.
        """
        # Si ya es una IP válida, devolverla
        if self.validate_ip(host):
            return host
        
        # Intentar resolver el dominio
        try:
            ip = socket.gethostbyname(host)
            return ip
        except (socket.gaierror, socket.herror, OSError) as e:
            # Si no se puede resolver, devolver el host original
            # El error se manejará en compare
            return host
    
    def measure_ping(self, host: str, count: int = 2) -> Dict[str, Any]:
        """
        Mide la latencia (ping) a un host.
        Retorna información sobre el tiempo de respuesta.
        Primero intenta usar subprocess, si falla usa ping3 como alternativa.
        Se usa count=2 por defecto para mejorar tiempo de respuesta.
        """
        system = platform.system().lower()
        
        # Intentar primero con subprocess (método nativo)
        try:
            if system == "windows":
                cmd = ["ping", "-n", str(count), host]
            else:
                # Linux, macOS, etc.
                cmd = ["ping", "-c", str(count), host]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Extraer información del ping
            ping_info = {
                "host": host,
                "stdout": result.stdout.strip(),
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
            
            # Intentar extraer tiempos de respuesta del output
            if result.returncode == 0:
                # Buscar tiempos en el output (formato varía según OS)
                time_patterns = [
                    r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms",  # Windows: time<1ms o time=10ms
                    r"time=(\d+(?:\.\d+)?)\s*ms",        # Linux/Mac: time=10.5ms
                    r"(\d+(?:\.\d+)?)\s*ms"              # Formato genérico
                ]
                
                times = []
                for pattern in time_patterns:
                    matches = re.findall(pattern, result.stdout, re.IGNORECASE)
                    if matches:
                        times = [float(t) for t in matches]
                        break
                
                if times:
                    ping_info["times"] = times
                    ping_info["min_time"] = min(times)
                    ping_info["max_time"] = max(times)
                    ping_info["avg_time"] = sum(times) / len(times)
                    ping_info["packet_loss"] = 0  # Si llegó aquí, no hay pérdida
                else:
                    ping_info["avg_time"] = None
            else:
                ping_info["avg_time"] = None
                ping_info["packet_loss"] = 100
                # Agregar mensaje de error cuando el ping falla
                if not ping_info.get("error"):
                    # Intentar extraer información del stderr o stdout
                    error_text = result.stderr.strip() if result.stderr else ""
                    if not error_text:
                        # Si no hay stderr, usar un mensaje genérico basado en el stdout
                        if "timeout" in result.stdout.lower() or "timed out" in result.stdout.lower():
                            ping_info["error"] = "Timeout: no se recibieron respuestas en el tiempo esperado"
                        elif "unreachable" in result.stdout.lower() or "no route" in result.stdout.lower():
                            ping_info["error"] = "Host inalcanzable: no se pudo establecer conexión"
                        else:
                            ping_info["error"] = "No se recibieron respuestas del servidor"
                    else:
                        ping_info["error"] = error_text
            
            return ping_info
            
        except subprocess.TimeoutExpired:
            # Si timeout, intentar con ping3, y si falla usar TCP
            result = self._ping_with_ping3(host, count)
            if not result.get("success"):
                return self._ping_with_tcp(host, count)
            return result
        except FileNotFoundError:
            # Si el comando no existe, usar ping3 como alternativa, y si falla usar TCP
            result = self._ping_with_ping3(host, count)
            if not result.get("success"):
                return self._ping_with_tcp(host, count)
            return result
        except Exception as e:
            # Si hay otro error, intentar con ping3, y si falla usar TCP
            result = self._ping_with_ping3(host, count)
            if not result.get("success"):
                return self._ping_with_tcp(host, count)
            return result
    
    def _ping_with_tcp(self, host: str, count: int = 2) -> Dict[str, Any]:
        """
        Método alternativo usando conexiones TCP cuando ICMP no está disponible.
        Este método funciona sin permisos especiales y es compatible con Heroku.
        """
        times = []
        successful_pings = 0
        
        # Resolver el host a IP si es necesario
        try:
            resolved_ip = self.resolve_domain(host)
        except Exception as e:
            return {
                "host": host,
                "error": f"No se pudo resolver el dominio: {str(e)}",
                "avg_time": None,
                "success": False
            }
        
        # Intentar puertos comunes (80 para HTTP, 443 para HTTPS)
        ports_to_try = [80, 443, 22]
        
        # Realizar múltiples pings
        for i in range(count):
            ping_time = None
            for port in ports_to_try:
                try:
                    # Crear socket y medir tiempo de conexión
                    start_time = time.time()
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex((resolved_ip, port))
                    end_time = time.time()
                    sock.close()
                    
                    if result == 0:
                        # Conexión exitosa
                        ping_time = (end_time - start_time) * 1000  # Convertir a milisegundos
                        successful_pings += 1
                        times.append(ping_time)
                        break  # Si un puerto funciona, no intentar los demás
                except socket.timeout:
                    # Timeout en este puerto, intentar el siguiente
                    continue
                except Exception as e:
                    # Error en este puerto, intentar el siguiente
                    continue
            
            # Si ningún puerto funcionó, esperar un poco antes del siguiente intento
            if ping_time is None:
                time.sleep(0.5)
        
        if times:
            ping_info = {
                "host": host,
                "resolved_ip": resolved_ip if resolved_ip != host else None,
                "stdout": f"Ping a {host} ({resolved_ip}): {successful_pings}/{count} paquetes recibidos (método TCP)",
                "returncode": 0,
                "success": True,
                "times": times,
                "min_time": min(times),
                "max_time": max(times),
                "avg_time": sum(times) / len(times),
                "packet_loss": ((count - successful_pings) / count) * 100
            }
            return ping_info
        else:
            return {
                "host": host,
                "resolved_ip": resolved_ip if resolved_ip != host else None,
                "stdout": f"Ping a {host} ({resolved_ip}): 0/{count} paquetes recibidos",
                "returncode": 1,
                "success": False,
                "error": "No se pudo establecer conexión TCP con ningún puerto común (80, 443, 22)",
                "avg_time": None,
                "packet_loss": 100
            }
    
    def _ping_with_ping3(self, host: str, count: int = 2) -> Dict[str, Any]:
        """
        Método alternativo usando la biblioteca ping3 cuando subprocess no está disponible.
        Nota: Este método puede fallar en entornos sin permisos de root (como Heroku).
        """
        if not PING3_AVAILABLE:
            # Si ping3 no está disponible, usar método TCP
            return self._ping_with_tcp(host, count)
        
        try:
            times = []
            successful_pings = 0
            
            # Resolver el host a IP si es necesario
            resolved_ip = self.resolve_domain(host)
            
            # Realizar múltiples pings
            for i in range(count):
                try:
                    # ping3.ping retorna el tiempo en segundos o None si falla
                    delay = ping3.ping(resolved_ip, timeout=5)
                    if delay is not None:
                        # Convertir a milisegundos
                        delay_ms = delay * 1000
                        times.append(delay_ms)
                        successful_pings += 1
                    else:
                        # Timeout o no respuesta
                        pass
                except (PermissionError, OSError) as e:
                    # Si no hay permisos (común en Heroku), usar método TCP
                    return self._ping_with_tcp(host, count)
                except Exception as e:
                    # Error en un ping individual, continuar con los siguientes
                    continue
            
            if times:
                ping_info = {
                    "host": host,
                    "resolved_ip": resolved_ip if resolved_ip != host else None,
                    "stdout": f"Ping a {host} ({resolved_ip}): {successful_pings}/{count} paquetes recibidos",
                    "returncode": 0 if successful_pings > 0 else 1,
                    "success": successful_pings > 0,
                    "times": times,
                    "min_time": min(times),
                    "max_time": max(times),
                    "avg_time": sum(times) / len(times),
                    "packet_loss": ((count - successful_pings) / count) * 100
                }
                return ping_info
            else:
                # Si ping3 no funcionó, intentar con TCP como fallback
                return self._ping_with_tcp(host, count)
                
        except (PermissionError, OSError) as e:
            # Si no hay permisos, usar método TCP
            return self._ping_with_tcp(host, count)
        except Exception as e:
            # Si hay otro error, intentar con TCP como fallback
            return self._ping_with_tcp(host, count)
    
    def measure_response_time(self, host: str) -> float:
        """
        Mide el tiempo de respuesta de un host usando socket.
        Retorna el tiempo en milisegundos o None si falla.
        """
        try:
            resolved_ip = self.resolve_domain(host)
            if not self.validate_ip(resolved_ip):
                return None
            
            # Crear socket y medir tiempo de conexión
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((resolved_ip, 80))  # Puerto 80 (HTTP)
            sock.close()
            end_time = time.time()
            
            if result == 0:
                return (end_time - start_time) * 1000  # Convertir a milisegundos
            else:
                return None
        except Exception:
            return None
    
    @cache_result("ip_compare", ttl=600)  # Cache por 10 minutos
    def compare(self, ip1: str, ip2: str) -> Dict[str, Any]:
        """
        Compara dos IPs o dominios y devuelve información detallada de la comparación.
        Incluye latencia, velocidad de respuesta, información de red y más.
        """
        # Resolver dominios a IPs si es necesario
        resolved_ip1 = self.resolve_domain(ip1)
        resolved_ip2 = self.resolve_domain(ip2)
        
        r = {
            "ip1": ip1,
            "ip2": ip2,
            "resolved_ip1": resolved_ip1 if resolved_ip1 != ip1 else None,
            "resolved_ip2": resolved_ip2 if resolved_ip2 != ip2 else None,
            "same_subnet": None,
            "comparison": None,
            "ping1": None,
            "ping2": None,
            "response_time1": None,
            "response_time2": None,
            "speed_comparison": None,
            "network_info": None
        }
        
        try:
            # Validar que las IPs resueltas sean válidas
            if not self.validate_ip(resolved_ip1):
                r["error"] = f"No se pudo resolver '{ip1}' a una IP válida"
                r["same_subnet"] = False
                return r
            
            if not self.validate_ip(resolved_ip2):
                r["error"] = f"No se pudo resolver '{ip2}' a una IP válida"
                r["same_subnet"] = False
                return r
            
            # Comparar las IPs (información de red)
            a = ipaddress.ip_network(f"{resolved_ip1}/24", strict=False)
            b = ipaddress.ip_network(f"{resolved_ip2}/24", strict=False)
            r["same_subnet"] = (a.network_address == b.network_address)
            
            # Medir latencia (ping) a ambas IPs
            r["ping1"] = self.measure_ping(resolved_ip1, count=3)
            r["ping2"] = self.measure_ping(resolved_ip2, count=3)
            
            # Medir tiempo de respuesta (conexión TCP)
            r["response_time1"] = self.measure_response_time(resolved_ip1)
            r["response_time2"] = self.measure_response_time(resolved_ip2)
            
            # Comparación de velocidad
            avg1 = r["ping1"].get("avg_time") if r["ping1"] and r["ping1"].get("avg_time") else None
            avg2 = r["ping2"].get("avg_time") if r["ping2"] and r["ping2"].get("avg_time") else None
            
            if avg1 is not None and avg2 is not None:
                if avg1 < avg2:
                    faster = ip1
                    slower = ip2
                    difference = avg2 - avg1
                    r["speed_comparison"] = f"{ip1} es más rápido: {avg1:.2f}ms vs {avg2:.2f}ms (diferencia: {difference:.2f}ms)"
                elif avg2 < avg1:
                    faster = ip2
                    slower = ip1
                    difference = avg1 - avg2
                    r["speed_comparison"] = f"{ip2} es más rápido: {avg2:.2f}ms vs {avg1:.2f}ms (diferencia: {difference:.2f}ms)"
                else:
                    r["speed_comparison"] = f"Ambas IPs tienen latencia similar: {avg1:.2f}ms"
            elif avg1 is not None:
                r["speed_comparison"] = f"{ip1} tiene latencia de {avg1:.2f}ms (no se pudo medir {ip2})"
            elif avg2 is not None:
                r["speed_comparison"] = f"{ip2} tiene latencia de {avg2:.2f}ms (no se pudo medir {ip1})"
            
            # Información de red
            if r["same_subnet"]:
                r["network_info"] = f"Las IPs {resolved_ip1} y {resolved_ip2} están en la misma subred (red local similar)"
            else:
                # Calcular distancia de red (diferencia en octetos)
                ip1_octets = resolved_ip1.split('.')
                ip2_octets = resolved_ip2.split('.')
                differences = sum(1 for i in range(4) if ip1_octets[i] != ip2_octets[i])
                r["network_info"] = f"Las IPs están en diferentes subredes (diferencia en {differences} octeto(s))"
            
            # Construir mensaje de comparación completo con conclusiones
            comparison_parts = []
            comparison_parts.append(f"### Comparación de Rendimiento: {ip1} vs {ip2}\\n")
            
            # Tabla de comparación directa
            comparison_parts.append("| Métrica | " + f"**{ip1}**" + " | " + f"**{ip2}**" + " | Diferencia |")
            comparison_parts.append("| :--- | :--- | :--- | :--- |")
            
            # IP Resuelta
            rip1 = r['resolved_ip1'] if r['resolved_ip1'] else "❌"
            rip2 = r['resolved_ip2'] if r['resolved_ip2'] else "❌"
            comparison_parts.append(f"| **IP** | **{rip1}** | **{rip2}** | - |")
            
            # Latencia AVG
            if avg1 is not None and avg2 is not None:
                diff_val = abs(avg1 - avg2)
                cell1 = f"{avg1:.2f} ms"
                cell2 = f"{avg2:.2f} ms"
                if avg1 < avg2:
                    cell1 = f"**{cell1}** 🏆"
                elif avg2 < avg1:
                    cell2 = f"**{cell2}** 🏆"
                
                comparison_parts.append(f"| **Latencia Promedio** | {cell1} | {cell2} | {diff_val:.2f} ms |")
                
                # Min/Max
                min1 = r['ping1'].get('min_time', avg1)
                max1 = r['ping1'].get('max_time', avg1)
                min2 = r['ping2'].get('min_time', avg2)
                max2 = r['ping2'].get('max_time', avg2)
                
                comparison_parts.append(f"| **Mínima** | {min1:.2f} ms | {min2:.2f} ms | - |")
                comparison_parts.append(f"| **Máxima** | {max1:.2f} ms | {max2:.2f} ms | - |")
                
                # Variabilidad (Jitter aprox)
                var1 = max1 - min1
                var2 = max2 - min2
                comparison_parts.append(f"| **Variabilidad** | {var1:.2f} ms | {var2:.2f} ms | - |")

            # Tiempo de respuesta TCP
            if r["response_time1"] is not None and r["response_time2"] is not None:
                rt1 = f"{r['response_time1']:.2f} ms"
                rt2 = f"{r['response_time2']:.2f} ms"
                comparison_parts.append(f"| **Respuesta TCP** | {rt1} | {rt2} | - |")
            
            comparison_parts.append("")
            
            # Conclusiones y análisis detallado MEJORADO
            comparison_parts.append(f"**Análisis Detallado**")
            comparison_parts.append("")
            
            if avg1 is not None and avg2 is not None:
                difference = abs(avg1 - avg2)
                percentage_diff = (difference / max(avg1, avg2)) * 100 if max(avg1, avg2) > 0 else 0
                
                if avg1 < avg2:
                    faster_host = ip1
                    faster_avg = avg1
                    slower_host = ip2
                    slower_avg = avg2
                else:
                    faster_host = ip2
                    faster_avg = avg2
                    slower_host = ip1
                    slower_avg = avg1
                
                # 1. Comparación de velocidad
                comparison_parts.append(f"**🏆 Ganador en Latencia: {faster_host}**")
                comparison_parts.append("")  # Línea vacía después del encabezado
                if difference < 5:
                    comparison_parts.append(f"• Diferencia: {difference:.2f}ms ({percentage_diff:.1f}%) - **Insignificante**, ambos ofrecen rendimiento similar.")
                elif percentage_diff < 20:
                    comparison_parts.append(f"• Diferencia: {difference:.2f}ms ({percentage_diff:.1f}%) - **{faster_host}** es ligeramente más rápido, pero no es crítico.")
                else:
                    comparison_parts.append(f"• Diferencia: {difference:.2f}ms ({percentage_diff:.1f}%) - **{faster_host}** es claramente superior.")
                comparison_parts.append("")
                
                # 2. Análisis individual de cada host
                comparison_parts.append(f"**Análisis de {ip1}:**")
                comparison_parts.append("")  # Línea vacía después del encabezado
                
                # Calidad de latencia para ip1
                if avg1 < 20:
                    comparison_parts.append(f"**• Latencia excelente** ({avg1:.2f}ms): Ideal para aplicaciones en tiempo real.")
                elif avg1 < 50:
                    comparison_parts.append(f"**• Latencia muy buena** ({avg1:.2f}ms): Adecuada para web y streaming.")
                elif avg1 < 100:
                    comparison_parts.append(f"**• Latencia aceptable** ({avg1:.2f}ms): Suficiente para navegación general.")
                elif avg1 < 200:
                    comparison_parts.append(f"**• Latencia moderada** ({avg1:.2f}ms): Puede afectar aplicaciones en tiempo real.")
                else:
                    comparison_parts.append(f"**• Latencia alta** ({avg1:.2f}ms): Puede causar retrasos notables.")
                    
                comparison_parts.append("")
                
                # Estabilidad para ip1
                var1 = (r['ping1'].get('max_time', avg1) - r['ping1'].get('min_time', avg1)) if r['ping1'] else 0
                if var1 < 5:
                    comparison_parts.append(f"**• Conexión muy estable** (jitter: {var1:.2f}ms).")
                elif var1 < 20:
                    comparison_parts.append(f"**• Conexión estable** (jitter: {var1:.2f}ms).")
                else:
                    comparison_parts.append(f"**• Conexión variable** (jitter: {var1:.2f}ms) - puede afectar aplicaciones sensibles.")
                
                comparison_parts.append("")
                
                # Pérdida de paquetes para ip1
                loss1 = r['ping1'].get('packet_loss', 0) if r['ping1'] else 0
                if loss1 == 0:
                    comparison_parts.append(f"• **Sin pérdida de paquetes** - Conexión confiable al 100%.")
                elif loss1 < 5:
                    comparison_parts.append(f"• Pérdida mínima ({loss1:.1f}%) - Generalmente confiable.")
                else:
                    comparison_parts.append(f"• Pérdida significativa ({loss1:.1f}%) - Problemas detectados.")
                
                comparison_parts.append("")
                comparison_parts.append(f"**Análisis de {ip2}:**")
                comparison_parts.append("")  # Línea vacía después del encabezado
                
                # Calidad de latencia para ip2
                if avg2 < 20:
                    comparison_parts.append(f"**• Latencia excelente** ({avg2:.2f}ms): Ideal para aplicaciones en tiempo real.")
                elif avg2 < 50:
                    comparison_parts.append(f"**• Latencia muy buena** ({avg2:.2f}ms): Adecuada para web y streaming.")
                elif avg2 < 100:
                    comparison_parts.append(f"**• Latencia aceptable** ({avg2:.2f}ms): Suficiente para navegación general.")
                elif avg2 < 200:
                    comparison_parts.append(f"**• Latencia moderada** ({avg2:.2f}ms): Puede afectar aplicaciones en tiempo real.")
                else:
                    comparison_parts.append(f"**• Latencia alta** ({avg2:.2f}ms): Puede causar retrasos notables.")
                    
                comparison_parts.append("")
                
                # Estabilidad para ip2
                var2 = (r['ping2'].get('max_time', avg2) - r['ping2'].get('min_time', avg2)) if r['ping2'] else 0
                if var2 < 5:
                    comparison_parts.append(f"**• Conexión muy estable** (jitter: {var2:.2f}ms).")
                elif var2 < 20:
                    comparison_parts.append(f"**• Conexión estable** (jitter: {var2:.2f}ms).")
                else:
                    comparison_parts.append(f"**• Conexión variable** (jitter: {var2:.2f}ms) - puede afectar aplicaciones sensibles.")
                    
                comparison_parts.append("")
                
                # Pérdida de paquetes para ip2
                loss2 = r['ping2'].get('packet_loss', 0) if r['ping2'] else 0
                if loss2 == 0:
                    comparison_parts.append(f"**• Sin pérdida de paquetes** - Conexión confiable al 100%.")
                elif loss2 < 5:
                    comparison_parts.append(f"**• Pérdida mínima ({loss2:.1f}%) - Generalmente confiable.")
                else:
                    comparison_parts.append(f"**• Pérdida significativa ({loss2:.1f}%) - Problemas detectados.")
                
                comparison_parts.append("")
                
                # 3. Recomendación final
                comparison_parts.append("**Conclusión:**")
                comparison_parts.append("")  # Línea vacía después del encabezado
                
                # Determinar el mejor host considerando latencia y estabilidad
                if difference < 5 and abs(var1 - var2) < 5:
                    comparison_parts.append(f"• Ambos hosts ofrecen rendimiento prácticamente idéntico. Puedes usar cualquiera.")
                elif faster_avg < 50 and var1 < var2 and faster_host == ip1:
                    comparison_parts.append(f"• **{faster_host}**: Mejor latencia ({faster_avg:.2f}ms) y más estable (jitter: {var1:.2f}ms).")
                elif faster_avg < 50 and var2 < var1 and faster_host == ip2:
                    comparison_parts.append(f"• **{faster_host}**: Mejor latencia ({faster_avg:.2f}ms) y más estable (jitter: {var2:.2f}ms).")
                elif faster_avg < 50:
                    comparison_parts.append(f"• **{faster_host}**: Ligeramente más rápido ({faster_avg:.2f}ms vs {slower_avg:.2f}ms), aunque ambos son buenos.")
                else:
                    comparison_parts.append(f"• **{faster_host}**: Significativamente mejor ({faster_avg:.2f}ms vs {slower_avg:.2f}ms).")
                
                # Análisis de pérdida de paquetes
                if loss1 > 0 or loss2 > 0:
                    if loss1 == loss2:
                        comparison_parts.append(f"• ⚠️ Ambos presentan la misma pérdida de paquetes ({loss1}%).")
                    elif loss1 < loss2:
                        comparison_parts.append(f"• **{ip1}**: Más confiable ({loss1}% pérdida vs {loss2}% de {ip2}).")
                    else:
                        comparison_parts.append(f"• **{ip2}**: Más confiable ({loss2}% pérdida vs {loss1}% de {ip1}).")
                else:
                    comparison_parts.append("• Ambos tienen 0% de pérdida de paquetes (conexión confiable).")
            
            comparison_parts.append("")
            
            if r["network_info"]:
                 comparison_parts.append(f"**• Topología de red:** {r['network_info']}")

            
            r["comparison"] = "\n".join(comparison_parts)
            r["summary"] = f"Comparación completa entre {ip1} y {ip2} con análisis detallado de latencia y conclusiones."
                
        except Exception as e:
            r["error"] = str(e)
            r["same_subnet"] = False
        
        return r

    @cache_result("ip_ping", ttl=300)  # Cache por 5 minutos (TTL corto para operaciones de red)
    def ping(self, host: str, count: int = 2) -> Dict[str, Any]:
        """
        Ejecuta un ping a la IP o dominio proporcionado.
        Retorna el resultado completo del ping con información de latencia.
        """
        ping_result = self.measure_ping(host, count)
        
        # Formatear resultado similar a tracert para consistencia
        if ping_result.get("success"):
            result = {
                "stdout": ping_result.get("stdout", ""),
                "stderr": "",
                "returncode": 0,
                "host": host,
                "type": "ping",
                "success": True,
                "avg_time": ping_result.get("avg_time"),
                "min_time": ping_result.get("min_time"),
                "max_time": ping_result.get("max_time"),
                "times": ping_result.get("times", []),
                "packet_loss": ping_result.get("packet_loss", 0),
                "resolved_ip": ping_result.get("resolved_ip")
            }
        else:
            # Cuando falla, asegurar que tenemos toda la información necesaria
            error_msg = ping_result.get("error")
            if not error_msg:
                # Si no hay mensaje de error explícito, crear uno basado en el resultado
                if ping_result.get("packet_loss") == 100:
                    error_msg = "No se recibieron respuestas del servidor"
                elif ping_result.get("returncode") != 0:
                    error_msg = "El ping falló sin recibir respuestas"
                else:
                    error_msg = "Error al ejecutar ping"
            
            result = {
                "stdout": ping_result.get("stdout", ""),
                "stderr": ping_result.get("error", ""),
                "returncode": ping_result.get("returncode", 1),
                "host": host,
                "type": "ping",
                "success": False,
                "error": error_msg,
                "packet_loss": ping_result.get("packet_loss", 100),
                "resolved_ip": ping_result.get("resolved_ip")
            }
        
        return result
    
    @cache_result("ip_traceroute", ttl=600)  # Cache por 10 minutos
    def tracert(self, host: str) -> Dict[str, Any]:
        """
        Ejecuta un traceroute a la IP o dominio proporcionado.
        Detecta el sistema operativo y usa el comando correcto (tracert en Windows, traceroute en Linux/Mac).
        """
        try:
            # Detectar el sistema operativo y usar el comando correcto
            system = platform.system().lower()
            if system == "windows":
                cmd = ["tracert", host]
            else:
                # Linux, macOS, etc.
                cmd = ["traceroute", host]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "host": host,
                "type": "traceroute"
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Traceroute a {host} tardó demasiado o fue bloqueado por la red.", "type": "traceroute"}
        except FileNotFoundError:
            return {"error": f"Comando traceroute no encontrado. Asegúrate de tener instalado 'traceroute' (Linux/Mac) o 'tracert' (Windows).", "type": "traceroute"}
        except Exception as e:
            return {"error": str(e), "type": "traceroute"}
    
    def format_result(self, result: Dict[str, Any]) -> str:
        """
        Formatea un resultado de IP tool a texto legible.
        Centraliza la lógica de formateo para evitar duplicación.
        
        Args:
            result: Resultado de ping, tracert o compare
        
        Returns:
            Texto formateado del resultado
        """
        if not isinstance(result, dict):
            return str(result)
        
        # Manejar errores
        if "error" in result:
            return f"Error: {result['error']}"
        
        # Formatear comparación
        if result.get("type") == "multiple_comparison":
            base_host = result.get("base_host", "N/A")
            comparisons = result.get("comparisons", [])
            summary = result.get("summary", "")
            
            parts = [summary or f"Comparación de {base_host} con {len(comparisons)} otros hosts:\n"]
            for comp in comparisons:
                host1 = comp.get("host1", "N/A")
                host2 = comp.get("host2", "N/A")
                comp_result = comp.get("comparison", {})
                
                if isinstance(comp_result, dict):
                    comparison_text = comp_result.get("comparison", "")
                    if comparison_text:
                        parts.append(f"\n{comparison_text}")
                    else:
                        parts.append(f"\nComparación entre {host1} y {host2}:")
                        if "network_info" in comp_result:
                            parts.append(f"  • {comp_result['network_info']}")
                        if "speed_comparison" in comp_result:
                            parts.append(f"  • {comp_result['speed_comparison']}")
            
            return "\n".join(parts)
        
        # Formatear comparación simple
        if "comparison" in result or ("ip1" in result and "ip2" in result):
            comparison_text = result.get("comparison", "")
            if comparison_text:
                return comparison_text
            else:
                # Fallback si no hay texto de comparación
                ip1 = result.get("ip1", "N/A")
                ip2 = result.get("ip2", "N/A")
                same_subnet = result.get("same_subnet", False)
                speed_comparison = result.get("speed_comparison", "")
                network_info = result.get("network_info", "")
                
                parts = [f"Comparación entre {ip1} y {ip2}:"]
                if network_info:
                    parts.append(f"  • {network_info}")
                if speed_comparison:
                    parts.append(f"  • {speed_comparison}")
                return "\n".join(parts)
        
        # Formatear ping
        if result.get("type") == "ping" or ("ping" in str(result).lower() and "stdout" in result):
            host = result.get("host", "N/A")
            ip_str = f" (**{result.get('resolved_ip')}**)" if result.get('resolved_ip') and result.get('resolved_ip') != host else ""
            
            # Determinar estado
            success = result.get("success", False)
            status_icon = "✅" if success else "❌"
            status_text = "Exitoso" if success else "Fallido"
            
            # Métricas (extraer valores numéricos para análisis)
            avg_time = result.get('avg_time')
            min_time = result.get('min_time')
            max_time = result.get('max_time')
            packet_loss = result.get('packet_loss', 0)
            
            avg = f"{avg_time:.2f} ms" if avg_time is not None else "N/A"
            min_t = f"{min_time:.2f} ms" if min_time is not None else "N/A"
            max_t = f"{max_time:.2f} ms" if max_time is not None else "N/A"
            loss = f"{packet_loss:.1f}%"
            
            # Construir reporte limpio y compacto (SIN stdout raw)
            md = [
                f"### Reporte de Ping: {host}{ip_str}",
                "",
                f"**Estado:** {status_text} {status_icon}",
                "",
                "| Mínima | Promedio | Máxima | Pérdida |",
                "| :---: | :---: | :---: | :---: |",
                f"| {min_t} | **{avg}** | {max_t} | {loss} |",
                ""
            ]

            # Detalles de paquetes individuales si existen
            times = result.get("times", [])
            if times:
                md.append("**Tiempos individuales:**")
                md.append("")
                # Crear tabla horizontal con los tiempos
                headers = " | ".join([f"Paquete {i+1}" for i in range(len(times))])
                md.append(f"| {headers} |")
                separators = " | ".join([":---:" for _ in times])
                md.append(f"| {separators} |")
                values = " | ".join([f"{t:.1f} ms" for t in times])
                md.append(f"| {values} |")
                md.append("")
                
            # Mensaje de error si falla
            if not success:
                error_msg = result.get("error", "No se recibieron respuestas")
                md.append(f"**❌ Error:** {error_msg}")
                md.append("")
            else:
                md.append("")
                md.append("### **Análisis y Conclusión**")
                md.append("")
                md.append("")
                
                conclusions = []
                
                # 1. Evaluar calidad de latencia
                if avg_time is not None:
                    if avg_time < 20:
                        conclusions.append("• **Latencia excelente** (< 20ms): Ideal para aplicaciones en tiempo real, gaming y videoconferencias.")
                        conclusions.append("")  # Línea vacía para interlineado
                    elif avg_time < 50:
                        conclusions.append("• **Latencia muy buena** (20-50ms): Adecuada para la mayoría de aplicaciones web y streaming.")
                        conclusions.append("")  # Línea vacía para interlineado
                    elif avg_time < 100:
                        conclusions.append("• **Latencia aceptable** (50-100ms): Suficiente para navegación web y aplicaciones generales.")
                        conclusions.append("")  # Línea vacía para interlineado
                    elif avg_time < 200:
                        conclusions.append("• **Latencia moderada** (100-200ms): Puede afectar aplicaciones en tiempo real.")
                        conclusions.append("")  # Línea vacía para interlineado
                    else:
                        conclusions.append("• **Latencia alta** (> 200ms): Puede causar retrasos notables en aplicaciones interactivas.")
                        conclusions.append("")  # Línea vacía para interlineado
                
                # 2. Evaluar estabilidad (jitter/variabilidad)
                if min_time is not None and max_time is not None:
                    jitter = max_time - min_time
                    if jitter < 5:
                        conclusions.append(f"• **Conexión muy estable**: Variabilidad mínima de {jitter:.2f}ms entre paquetes.")
                        conclusions.append("")  # Línea vacía para interlineado
                    elif jitter < 20:
                        conclusions.append(f"• **Conexión estable**: Variabilidad moderada de {jitter:.2f}ms.")
                        conclusions.append("")  # Línea vacía para interlineado
                    else:
                        conclusions.append(f"• **Conexión variable**: Jitter de {jitter:.2f}ms puede afectar aplicaciones sensibles a latencia.")
                        conclusions.append("")  # Línea vacía para interlineado
                
                # 3. Evaluar pérdida de paquetes
                if packet_loss == 0:
                    conclusions.append("• **Sin pérdida de paquetes**: Conexión confiable al 100%.")
                    conclusions.append("")  # Línea vacía para interlineado
                elif packet_loss < 5:
                    conclusions.append(f"• **Pérdida mínima** ({packet_loss:.1f}%): Conexión generalmente confiable.")
                    conclusions.append("")  # Línea vacía para interlineado
                elif packet_loss < 10:
                    conclusions.append(f"• **Pérdida moderada** ({packet_loss:.1f}%): Puede afectar la calidad de servicio.")
                    conclusions.append("")  # Línea vacía para interlineado
                else:
                    conclusions.append(f"• **Pérdida significativa** ({packet_loss:.1f}%): Problemas de conectividad detectados.")
                    conclusions.append("")  # Línea vacía para interlineado
                
                # 4. Análisis de tiempos individuales (si hay datos)
                if times and len(times) > 1:
                    # Detectar picos anormales
                    avg_of_times = sum(times) / len(times)
                    outliers = [t for t in times if abs(t - avg_of_times) > (avg_of_times * 0.5)]
                    if outliers:
                        conclusions.append(f"• **Picos detectados**: {len(outliers)} paquete(s) con latencia anormal, posible congestión intermitente.")
                        conclusions.append("")  # Línea vacía para interlineado
                
                # Agregar conclusiones al reporte
                md.extend(conclusions)
                md.append("")

            return "\n".join(md)
        
        # Formatear múltiples pings
        if result.get("type") == "multiple_ping":
            ping_results = result.get("results", [])
            parts = [f"Ping ejecutado a {len(ping_results)} hosts:\n"]
            for ping_result in ping_results:
                host = ping_result.get("host", "N/A")
                stdout = ping_result.get("stdout", "")
                avg_time = ping_result.get("avg_time")
                parts.append(f"\n{host}:")
                if stdout:
                    parts.append(stdout)
                if avg_time is not None:
                    parts.append(f"Latencia promedio: {avg_time:.2f}ms")
            return "\n".join(parts)
        
        # Formatear traceroute
        if "traceroute" in result or ("stdout" in result and result.get("type") == "traceroute"):
            host = result.get("host", "N/A")
            stdout = result.get("stdout", "")
            
            md = [
                f"### 🗺️ Traceroute: {host}",
                "",
                "```text",
                stdout,
                "```"
            ]
            return "\n".join(md)
        
        # Fallback: convertir a string
        return str(result)