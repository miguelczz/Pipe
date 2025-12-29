from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import ipaddress
import requests
import socket
from typing import List, Optional, Dict, Any

router = APIRouter(prefix="/tools", tags=["Quick Tools"])

# --- Quick Tools Endpoints Removed by User Request ---
# (Subnet, DNS, MAC Lookup deleted)

# --- Dashboard Endpoints ---

class ServiceStatus(BaseModel):
    name: str
    status: str  # "operational", "degraded", "down"
    latency_ms: float
    uptime_percentage: float

class DashboardStats(BaseModel):
    active_incidents: int
    avg_latency: float
    services: List[ServiceStatus]

import time

@router.get("/dashboard/status", response_model=DashboardStats)
async def get_dashboard_status():
    # En entornos Cloud (Heroku, AWS), ICMP (Ping) suele estar bloqueado.
    # Usamos peticiones HTTP (TCP) para medir la latencia y disponibilidad real.
    
    targets = [
        {"name": "Internet (Google)", "url": "http://www.google.com"},
        {"name": "Gateway (Cloudflare)", "url": "http://1.1.1.1"}, 
        {"name": "Sistema NetMind", "url": "http://example.com"}
    ]
    
    services = []
    total_latency = 0
    
    def measure_http_latency(url: str) -> float:
        try:
            start_time = time.time()
            # HEAD es rápido y suficiente para comprobar conectividad
            requests.head(url, timeout=2.0)
            end_time = time.time()
            return round((end_time - start_time) * 1000, 2)
        except:
            return 999.0 # Timeout o error de conexión

    for t in targets:
        latency = measure_http_latency(t["url"])
        
        # Lógica de estado
        metric_value = latency
        status = "operational"
        
        if latency >= 999.0:
            status = "down"
        elif latency > 500:
            status = "degraded"
            
        total_latency += metric_value
        
        # Mapeamos nombres amigables para el frontend
        display_name = t["name"]
        
        services.append(ServiceStatus(
            name=display_name,
            status=status,
            latency_ms=metric_value,
            uptime_percentage=100.0 if status == "operational" else (50.0 if status == "degraded" else 0.0)
        ))
        
    avg = total_latency / len(targets) if targets else 0
    
    # Active incidents: count of non-operational services
    active_incidents = sum(1 for s in services if s.status != "operational")
    
    return DashboardStats(
        active_incidents=active_incidents,
        avg_latency=round(avg, 2),
        services=services
    )

# --- GeoTrace Endpoints ---

class GeoPoint(BaseModel):
    hop: int
    ip: str
    lat: float
    lon: float
    city: str
    country: str
    rtt: str

@router.get("/geo-trace", response_model=List[GeoPoint])
async def geo_trace(host: str = Query(..., description="Host to trace")):
    # 1. Run Traceroute
    # Implementation depends on OS. We'll reuse ip_tool logic or simple subprocess here for simplicity
    # Ideally import IPTool instance
    import subprocess
    import platform
    import re
    
    hops_ips = []
    
    # En entornos Cloud (Heroku), no tenemos permisos para raw sockets (ICMP).
    # Solución: Usamos una API externa (Looking Glass) para obtener la traza real.
    try:
        # Usamos la API de HackerTarget para obtener un MTR (Traceroute + Ping)
        # Esto nos da los saltos reales desde un servidor en internet hacia el destino
        response = requests.get(f"https://api.hackertarget.com/mtr/?q={host}", timeout=15)
        
        if response.status_code == 200:
            # El output es texto plano tipo MTR:
            # Host             Loss%   Snt   Last   Avg  Best  Wrst StDev
            # 1. 45.79.x.x      0.0%    10    0.4   0.5   0.4   1.2   0.2
            # 2. 172.x.x.x      0.0%    10    1.2   3.4   1.1  15.0   4.0
            
            lines = response.text.split('\n')
            for line in lines:
                # Buscamos líneas que empiecen con número de salto (ej: " 1.")
                # y extraemos la IP (que suele ser el segundo campo o estar entre paréntesis)
                if not line or "Loss%" in line: continue
                
                # Regex para encontrar IPs
                ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                if ip_match:
                    ip = ip_match.group(1)
                    # Evitamos duplicados consecutivos y la IP 0.0.0.0 o???
                    if ip not in hops_ips:
                        hops_ips.append(ip)
        else:
            raise Exception("API error")

    except Exception as e:
        print(f"External Trace failed: {e}")
        # Si falla la API externa, intentamos el traceroute local (por si estamos en local dev)
        try:
             import platform
             cmd = ['tracert', '-d', '-h', '10', host] if platform.system().lower() == 'windows' else ['traceroute', '-n', '-m', '10', host]
             proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             out, err = proc.communicate(timeout=10)
             for line in out.split('\n'):
                ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                if ip_match:
                    hops_ips.append(ip_match.group(1))
        except:
             pass
        
    if not hops_ips:
        # Último recurso: Resolver destino final
        try:
             target_ip = socket.gethostbyname(host)
             hops_ips.append(target_ip)
        except:
             raise HTTPException(status_code=400, detail="Could not trace host")

    # 2. Geolocation (Batch query to ip-api.com)
    # Max 100 IPs per batch. We have max 15 hops.
    # Docs: https://ip-api.com/docs/api:batch
    
    geo_points = []
    
    try:
        resp = requests.post("http://ip-api.com/batch", json=hops_ips, timeout=10)
        start_lat = None
        start_lon = None
        
        if resp.status_code == 200:
            data = resp.json()
            for idx, item in enumerate(data):
                if item.get("status") == "success":
                    lat = item.get("lat")
                    lon = item.get("lon")
                    
                    # Filter out local IPs or invalid coords
                    if lat == 0 and lon == 0: continue
                    
                    # Store current user location approximately from first public hop
                    # (Private IPs will fail status or have 0,0 usually but ip-api handles private IPs by failing)
                    
                    geo_points.append(GeoPoint(
                        hop=idx + 1,
                        ip=item.get("query"),
                        lat=lat,
                        lon=lon,
                        city=item.get("city", "Unknown"),
                        country=item.get("country", "Unknown"),
                        rtt="-" # Parsing RTT is complex, skipping for MVP
                    ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GeoIP Error: {str(e)}")
        
    return geo_points
