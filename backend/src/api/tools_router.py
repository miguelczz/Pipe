from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import ipaddress
import requests
import socket
from typing import List, Optional, Dict, Any

router = APIRouter(prefix="/tools", tags=["Quick Tools"])

class SubnetResult(BaseModel):
    cidr: str
    network_address: str
    broadcast_address: str
    netmask: str
    hostmask: str
    total_hosts: int
    usable_hosts: int
    first_host: str
    last_host: str
    ip_class: str
    is_private: bool

class DNSRecord(BaseModel):
    type: str
    value: str
    ttl: Optional[int] = None

class DNSResult(BaseModel):
    domain: str
    records: List[DNSRecord]

@router.get("/subnet-calc", response_model=SubnetResult)
async def subnet_calculator(cidr: str = Query(..., description="CIDR block or IP/Mask (e.g., 192.168.1.0/24)")):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        
        # Determine IP Class (Rough approximation for IPv4)
        first_octet = int(str(network.network_address).split('.')[0])
        ip_class = "Unknown"
        if 1 <= first_octet <= 126: ip_class = "A"
        elif 128 <= first_octet <= 191: ip_class = "B"
        elif 192 <= first_octet <= 223: ip_class = "C"
        elif 224 <= first_octet <= 239: ip_class = "D (Multicast)"
        elif 240 <= first_octet <= 255: ip_class = "E (Experimental)"

        return SubnetResult(
            cidr=str(network),
            network_address=str(network.network_address),
            broadcast_address=str(network.broadcast_address),
            netmask=str(network.netmask),
            hostmask=str(network.hostmask),
            total_hosts=network.num_addresses,
            usable_hosts=max(0, network.num_addresses - 2) if network.prefixlen < 31 else max(0, network.num_addresses),
            first_host=str(network[1]) if network.num_addresses > 2 else str(network[0]),
            last_host=str(network[-2]) if network.num_addresses > 2 else str(network[-1]),
            ip_class=ip_class,
            is_private=network.is_private
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/dns-lookup", response_model=DNSResult)
async def dns_lookup(domain: str = Query(..., description="Domain name")):
    try:
        import dns.resolver
        
        records = []
        record_types = ['A', 'AAAA', 'MX', 'TXT', 'NS', 'CNAME']
        
        for r_type in record_types:
            try:
                answers = dns.resolver.resolve(domain, r_type)
                for rdata in answers:
                    records.append(DNSRecord(
                        type=r_type,
                        value=rdata.to_text(),
                        ttl=answers.ttl
                    ))
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                continue
            except Exception:
                continue
                
        if not records:
             # Fallback to basic socket lookup if DNS resolver fails completely or returns nothing specific
             try:
                 ip = socket.gethostbyname(domain)
                 records.append(DNSRecord(type='A', value=ip))
             except:
                 pass

        return DNSResult(domain=domain, records=records)
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@router.get("/mac-lookup")
async def mac_lookup(mac: str = Query(..., description="MAC Address")):
    try:
        # Using macvendors.co free API (No key required, rate limited but sufficient for basic tool)
        clean_mac = mac.replace(":", "").replace("-", "").replace(".", "")
        if len(clean_mac) < 6:
             raise ValueError("Invalid MAC Address")
             
        # Use simple requests with timeout
        response = requests.get(f"https://macvendors.co/api/{clean_mac}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # The API returns structured data under 'result', or sometimes directly
            return data.get("result", {"company": "Unknown", "address": "Unknown"})
        else:
            return {"company": "Not Found", "error": "API Error"}
            
    except Exception as e:
        # Don't fail hard on external API issues, just return not found
        return {"company": "Lookup Failed", "error": str(e)}

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

@router.get("/dashboard/status", response_model=DashboardStats)
async def get_dashboard_status():
    # In a real app, this would query a background monitoring service or DB
    # For now, we perform real-time check on key targets
    
    targets = [
        {"name": "Internet (Google DNS)", "host": "8.8.8.8"},
        {"name": "Gateway", "host": "1.1.1.1"}, # Cloudflare as proxy for external connectivity
        {"name": "Internal Auth", "host": "localhost"} # Dummy internal
    ]
    
    services = []
    total_latency = 0
    count_up = 0
    
    import platform
    import subprocess
    import re
    
    # Simple ping helper (non-blocking ideally, but blocking for MVP)
    def simple_ping(host):
        param = '-n' if platform.system().lower()=='windows' else '-c'
        # Timeout 1s (1000ms)
        command = ['ping', param, '1', host]
        try:
            # Short timeout to avoid blocking main thread too long
            output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
            if output.returncode == 0:
                # Extract time
                match = re.search(r"time[=<](\d+)", output.stdout)
                if match:
                    return float(match.group(1))
                return 1.0 # <1ms
            return None
        except:
            return None

    for t in targets:
        latency = simple_ping(t["host"])
        status = "down"
        if latency is not None:
            status = "operational" if latency < 100 else "degraded"
            total_latency += latency
            count_up += 1
        else:
            latency = 999.0
            
        services.append(ServiceStatus(
            name=t["name"],
            status=status,
            latency_ms=latency,
            uptime_percentage=99.9 if status != "down" else 0.0
        ))
        
    avg = total_latency / count_up if count_up > 0 else 0
    
    return DashboardStats(
        active_incidents=len(targets) - count_up,
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
    
    # Simplified traceroute for demo (captures IPs)
    # Using 'tracert -d' on windows to avoid DNS lookup delay, 'traceroute -n' on linux
    cmd = ['tracert', '-d', '-h', '15', host] if platform.system().lower() == 'windows' else ['traceroute', '-n', '-m', '15', host]
    
    try:
        # Run traceroute (this can take time, in prod use async task/process)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # We handle output line by line or wait
        out, err = proc.communicate(timeout=30) 
        
        # Parse IPs from output
        # Windows: "  1    <1 ms    <1 ms    <1 ms  192.168.1.1"
        # Linux: " 1  192.168.1.1  0.123 ms"
        
        lines = out.split('\n')
        for line in lines:
            # Find IPv4 address
            ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
            if ip_match:
                ip = ip_match.group(1)
                # Avoid duplicates if multiple RTTs show same IP? Usually one IP per line
                hops_ips.append(ip)
                
    except Exception as e:
        # If traceroute fails or timeouts, we might still have some hops
        pass
        
    if not hops_ips:
        # Fallback for demo if traceroute fails: just resolve the host
        try:
             hops_ips.append(socket.gethostbyname(host))
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
