"""
Herramienta DNS - Consultas de registros DNS para dominios.
Encapsula la lógica de resolución sin gestionar logging de infraestructura.
"""
from typing import Dict, Any, List, Optional

# Import opcional de dnspython
try:
    import dns.resolver
    import dns.reversename
    import dns.exception
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False


class DNSTool:
    """
    Herramienta para realizar consultas DNS.
    Soporta múltiples tipos de registros: A, AAAA, MX, TXT, NS, CNAME, PTR
    """
    
    def __init__(self):
        """Inicializa la herramienta DNS"""
        self.supported_record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "PTR"]
    
    def validate_domain(self, domain: str) -> bool:
        """
        Valida si un string es un dominio válido.
        
        Args:
            domain: String a validar
        
        Returns:
            True si es un dominio válido
        """
        if not domain or not isinstance(domain, str):
            return False
        
        # Patrón básico de dominio
        import re
        domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
        return bool(re.match(domain_pattern, domain.strip()))
    
    def query(self, domain: str, record_type: str = "A") -> Dict[str, Any]:
        """
        Consulta un registro DNS específico de un dominio.
        
        Args:
            domain: Dominio a consultar (ej: "google.com")
            record_type: Tipo de registro (A, AAAA, MX, TXT, NS, CNAME)
        
        Returns:
            Dict con los resultados de la consulta o error
        """
        if not DNS_AVAILABLE:
            return {
                "error": "dnspython no está instalado. Instala con: pip install dnspython",
                "domain": domain,
                "type": record_type,
                "success": False
            }
        
        if not self.validate_domain(domain):
            return {
                "error": f"'{domain}' no es un dominio válido",
                "domain": domain,
                "type": record_type
            }
        
        record_type = record_type.upper()
        if record_type not in self.supported_record_types:
            return {
                "error": f"Tipo de registro '{record_type}' no soportado. Tipos válidos: {', '.join(self.supported_record_types)}",
                "domain": domain,
                "type": record_type
            }
        
        try:
            answers = dns.resolver.resolve(domain, record_type)
            records = []
            
            for rdata in answers:
                if record_type == "MX":
                    # MX records tienen prioridad y exchange
                    records.append({
                        "priority": rdata.preference,
                        "exchange": str(rdata.exchange)
                    })
                else:
                    records.append(str(rdata))
            
            return {
                "domain": domain,
                "type": record_type,
                "records": records,
                "count": len(records),
                "success": True
            }
            
        except dns.resolver.NXDOMAIN:
            return {
                "error": f"Dominio '{domain}' no existe (NXDOMAIN)",
                "domain": domain,
                "type": record_type,
                "success": False
            }
        except dns.resolver.NoAnswer:
            return {
                "error": f"No se encontraron registros de tipo '{record_type}' para '{domain}'",
                "domain": domain,
                "type": record_type,
                "success": False
            }
        except dns.resolver.Timeout:
            return {
                "error": f"Timeout al consultar '{domain}'",
                "domain": domain,
                "type": record_type,
                "success": False
            }
        except dns.exception.DNSException as e:
            return {
                "error": f"Error DNS: {str(e)}",
                "domain": domain,
                "type": record_type,
                "success": False
            }
        except Exception as e:
            return {
                "error": f"Error inesperado: {str(e)}",
                "domain": domain,
                "type": record_type,
                "success": False
            }
    
    def get_all_records(self, domain: str) -> Dict[str, Any]:
        """
        Obtiene múltiples tipos de registros DNS para un dominio.
        Consulta A, AAAA, MX, TXT, NS y CNAME.
        
        Args:
            domain: Dominio a consultar
        
        Returns:
            Dict con todos los registros encontrados organizados por tipo
        """
        if not DNS_AVAILABLE:
            return {
                "error": "dnspython no está instalado. Instala con: pip install dnspython",
                "domain": domain
            }
        
        if not self.validate_domain(domain):
            return {
                "error": f"'{domain}' no es un dominio válido",
                "domain": domain
            }
        
        result = {
            "domain": domain,
            "records": {},
            "summary": []
        }
        
        # Tipos de registros a consultar
        record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
        
        for record_type in record_types:
            query_result = self.query(domain, record_type)
            if query_result.get("success") and "records" in query_result:
                result["records"][record_type] = query_result["records"]
                result["summary"].append(
                    f"{record_type}: {len(query_result['records'])} registro(s)"
                )
            elif "error" in query_result:
                # Solo registrar errores no críticos (NoAnswer es común)
                if "NoAnswer" not in query_result.get("error", ""):
                    pass
        
        # Construir mensaje de resumen detallado con todos los registros
        summary_parts = [f"Registros DNS para {domain}:"]
        
        # Diccionario con explicaciones de cada tipo
        type_explanations = {
            "A": "Registros A (IPv4): Mapean el dominio a direcciones IPv4",
            "AAAA": "Registros AAAA (IPv6): Mapean el dominio a direcciones IPv6",
            "MX": "Registros MX (Mail Exchange): Definen servidores de correo",
            "TXT": "Registros TXT: Contienen información de texto (verificación, SPF, seguridad)",
            "NS": "Registros NS (Name Server): Definen servidores de nombres autoritativos",
            "CNAME": "Registros CNAME: Crean alias que apuntan a otros dominios"
        }
        
        for record_type in ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]:
            if record_type in result["records"] and result["records"][record_type]:
                records = result["records"][record_type]
                summary_parts.append(f"\n{type_explanations.get(record_type, f'Registros {record_type}')}:")
                
                if record_type == "MX":
                    for record in records:
                        if isinstance(record, dict):
                            summary_parts.append(f"  • Prioridad {record.get('priority', 'N/A')}: {record.get('exchange', 'N/A')}")
                        else:
                            summary_parts.append(f"  • {record}")
                elif record_type == "TXT":
                    # Para TXT, agregar explicación adicional
                    summary_parts.append("  (Incluye verificaciones de dominio, SPF para email, y configuraciones de seguridad)")
                    for record in records:
                        summary_parts.append(f"  • {record}")
                else:
                    for record in records:
                        summary_parts.append(f"  • {record}")
        
        if len(summary_parts) > 1:  # Si hay más que solo el título
            result["summary_text"] = "\n".join(summary_parts)
        else:
            result["summary_text"] = f"No se encontraron registros DNS para {domain}"
            result["error"] = "No se encontraron registros DNS"
        
        return result
    
    def compare_dns(self, domain1: str, domain2: str) -> Dict[str, Any]:
        """
        Compara los registros DNS de dos dominios.
        Útil para usuarios que quieren comparar configuraciones DNS entre dominios.
        
        Args:
            domain1: Primer dominio a comparar
            domain2: Segundo dominio a comparar
        
        Returns:
            Dict con comparación detallada de registros DNS
        """
        if not DNS_AVAILABLE:
            return {
                "error": "dnspython no está instalado. Instala con: pip install dnspython",
                "domain1": domain1,
                "domain2": domain2
            }
        
        # Validar dominios
        if not self.validate_domain(domain1):
            return {"error": f"'{domain1}' no es un dominio válido", "domain1": domain1, "domain2": domain2}
        if not self.validate_domain(domain2):
            return {"error": f"'{domain2}' no es un dominio válido", "domain1": domain1, "domain2": domain2}
        
        # Obtener todos los registros de ambos dominios
        records1 = self.get_all_records(domain1)
        records2 = self.get_all_records(domain2)
        
        if "error" in records1 and "records" not in records1:
            return {"error": f"Error al obtener registros de {domain1}: {records1.get('error', 'error desconocido')}"}
        if "error" in records2 and "records" not in records2:
            return {"error": f"Error al obtener registros de {domain2}: {records2.get('error', 'error desconocido')}"}
        
        # Construir comparación
        comparison = {
            "domain1": domain1,
            "domain2": domain2,
            "type": "dns_comparison"
        }
        
        # Comparar cada tipo de registro
        all_record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
        comparison_parts = [f"### 🌐 Comparación DNS: {domain1} vs {domain2}\\n"]
        
        for record_type in all_record_types:
            records_d1 = records1.get("records", {}).get(record_type, [])
            records_d2 = records2.get("records", {}).get(record_type, [])
            
            if records_d1 or records_d2:
                comparison_parts.append(f"#### Registro **{record_type}**")
                
                # Comparar cantidad
                count1 = len(records_d1)
                count2 = len(records_d2)
                
                # Comparar valores según tipo
                match_status = "❌ Diferentes"
                details = []

                if record_type == "A" or record_type == "AAAA":
                    if set(records_d1) == set(records_d2) and count1 > 0:
                        match_status = "✅ Iguales"
                    details.append(f"- **{domain1}:** `{', '.join(records_d1) if records_d1 else 'Sin registros'}`")
                    details.append(f"- **{domain2}:** `{', '.join(records_d2) if records_d2 else 'Sin registros'}`")
                
                elif record_type == "MX":
                    # Comparar servidores de correo
                    mx1 = [r.get('exchange', '') if isinstance(r, dict) else str(r) for r in records_d1]
                    mx2 = [r.get('exchange', '') if isinstance(r, dict) else str(r) for r in records_d2]
                    if set(mx1) == set(mx2) and count1 > 0:
                        match_status = "✅ Iguales"
                    
                    details.append(f"- **{domain1}:** `{', '.join(mx1) if mx1 else 'Sin registros'}`")
                    details.append(f"- **{domain2}:** `{', '.join(mx2) if mx2 else 'Sin registros'}`")
                
                elif record_type == "NS":
                    # Comparar nameservers
                    if set(records_d1) == set(records_d2) and count1 > 0:
                        match_status = "✅ Iguales"
                        
                    details.append(f"- **{domain1}:** `{', '.join(records_d1) if records_d1 else 'Sin registros'}`")
                    details.append(f"- **{domain2}:** `{', '.join(records_d2) if records_d2 else 'Sin registros'}`")
                
                elif record_type == "TXT":
                    if count1 == count2:
                        match_status = "ℹ️ Cantidad igual"
                    details.append(f"- **{domain1}:** {count1} registro(s)")
                    details.append(f"- **{domain2}:** {count2} registro(s)")
                
                else:
                    if set(records_d1) == set(records_d2) and count1 > 0:
                         match_status = "✅ Iguales"
                    details.append(f"- **{domain1}:** {count1} registro(s)")
                    details.append(f"- **{domain2}:** {count2} registro(s)")

                comparison_parts.append(f"**Estado:** {match_status}")
                comparison_parts.extend(details)
                comparison_parts.append("")
        
        comparison["comparison"] = "\n".join(comparison_parts)
        comparison["summary_text"] = "\n".join(comparison_parts)
        comparison["success"] = True
        
        return comparison
    
    def check_spf(self, domain: str) -> Dict[str, Any]:
        """
        Verifica si un dominio tiene configuración SPF (Sender Policy Framework) para email.
        Útil para usuarios que quieren verificar la configuración de email de un dominio.
        
        Args:
            domain: Dominio a verificar
        
        Returns:
            Dict con información sobre SPF
        """
        txt_result = self.query(domain, "TXT")
        
        if not txt_result.get("success"):
            return {
                "domain": domain,
                "has_spf": False,
                "spf_record": None,
                "message": f"No se encontraron registros TXT para {domain}"
            }
        
        # Buscar registro SPF en los TXT
        spf_records = []
        for record in txt_result.get("records", []):
            if isinstance(record, str) and record.lower().startswith("v=spf1"):
                spf_records.append(record)
        
        if spf_records:
            return {
                "domain": domain,
                "has_spf": True,
                "spf_record": spf_records[0],
                "spf_records": spf_records,
                "message": f"El dominio {domain} tiene configuración SPF"
            }
        else:
            return {
                "domain": domain,
                "has_spf": False,
                "spf_record": None,
                "message": f"El dominio {domain} NO tiene configuración SPF en sus registros TXT"
            }
    
    def check_dmarc(self, domain: str) -> Dict[str, Any]:
        """
        Verifica si un dominio tiene configuración DMARC.
        Útil para verificar protección contra phishing en email.
        
        Args:
            domain: Dominio a verificar
        
        Returns:
            Dict con información sobre DMARC
        """
        txt_result = self.query(domain, "TXT")
        
        if not txt_result.get("success"):
            return {
                "domain": domain,
                "has_dmarc": False,
                "dmarc_record": None,
                "message": f"No se encontraron registros TXT para {domain}"
            }
        
        # Buscar registro DMARC (puede estar en _dmarc subdominio o en TXT)
        dmarc_records = []
        for record in txt_result.get("records", []):
            if isinstance(record, str) and record.lower().startswith("v=dmarc1"):
                dmarc_records.append(record)
        
        # También verificar en _dmarc subdominio
        try:
            dmarc_subdomain_result = self.query(f"_dmarc.{domain}", "TXT")
            if dmarc_subdomain_result.get("success"):
                for record in dmarc_subdomain_result.get("records", []):
                    if isinstance(record, str) and record.lower().startswith("v=dmarc1"):
                        dmarc_records.append(record)
        except Exception:
            pass
        
        if dmarc_records:
            return {
                "domain": domain,
                "has_dmarc": True,
                "dmarc_record": dmarc_records[0],
                "dmarc_records": dmarc_records,
                "message": f"El dominio {domain} tiene configuración DMARC"
            }
        else:
            return {
                "domain": domain,
                "has_dmarc": False,
                "dmarc_record": None,
                "message": f"El dominio {domain} NO tiene configuración DMARC"
            }
    
    def get_domain_info(self, domain: str) -> Dict[str, Any]:
        """
        Obtiene información completa y útil de un dominio para usuarios normales.
        Incluye: IPs, servidores de correo, verificación de seguridad (SPF, DMARC), nameservers.
        
        Args:
            domain: Dominio a analizar
        
        Returns:
            Dict con información completa y formateada para usuarios
        """
        if not self.validate_domain(domain):
            return {"error": f"'{domain}' no es un dominio válido", "domain": domain}
        
        result = {
            "domain": domain,
            "info": {}
        }
        
        # Obtener registros principales
        all_records = self.get_all_records(domain)
        
        # Información de IPs
        a_records = all_records.get("records", {}).get("A", [])
        aaaa_records = all_records.get("records", {}).get("AAAA", [])
        result["info"]["ips"] = {
            "ipv4": a_records,
            "ipv6": aaaa_records,
            "has_ipv4": len(a_records) > 0,
            "has_ipv6": len(aaaa_records) > 0
        }
        
        # Información de email
        mx_records = all_records.get("records", {}).get("MX", [])
        spf_info = self.check_spf(domain)
        dmarc_info = self.check_dmarc(domain)
        
        result["info"]["email"] = {
            "mail_servers": mx_records,
            "has_mail_servers": len(mx_records) > 0,
            "spf": spf_info,
            "dmarc": dmarc_info
        }
        
        # Información de nameservers
        ns_records = all_records.get("records", {}).get("NS", [])
        result["info"]["nameservers"] = {
            "servers": ns_records,
            "count": len(ns_records)
        }
        
        # Construir resumen legible
        summary_parts = [f"Información completa del dominio {domain}:\n"]
        
        # IPs
        if a_records:
            summary_parts.append(f"\n📍 Direcciones IP (IPv4): {', '.join(a_records)}")
        if aaaa_records:
            summary_parts.append(f"📍 Direcciones IP (IPv6): {', '.join(aaaa_records)}")
        
        # Email
        if mx_records:
            mx_list = [r.get('exchange', '') if isinstance(r, dict) else r for r in mx_records]
            summary_parts.append(f"\n📧 Servidores de correo: {', '.join(mx_list)}")
        else:
            summary_parts.append(f"\n📧 Servidores de correo: No configurados")
        
        summary_parts.append(f"📧 SPF (protección email): {'✅ Configurado' if spf_info.get('has_spf') else '❌ No configurado'}")
        summary_parts.append(f"📧 DMARC (anti-phishing): {'✅ Configurado' if dmarc_info.get('has_dmarc') else '❌ No configurado'}")
        
        # Nameservers
        if ns_records:
            summary_parts.append(f"\n🌐 Nameservers: {', '.join(ns_records)}")
        
        result["summary"] = "\n".join(summary_parts)
        result["summary_text"] = "\n".join(summary_parts)
        result["success"] = True
        
        return result
    
    def reverse_lookup(self, ip: str) -> Dict[str, Any]:
        """
        Realiza una búsqueda inversa DNS (PTR) para una IP.
        
        Args:
            ip: Dirección IP (IPv4 o IPv6)
        
        Returns:
            Dict con el nombre de dominio asociado a la IP
        """
        if not DNS_AVAILABLE:
            return {
                "error": "dnspython no está instalado. Instala con: pip install dnspython",
                "ip": ip,
                "success": False
            }
        
        try:
            import ipaddress
            # Validar que sea una IP válida
            ipaddress.ip_address(ip)
            
            # Convertir IP a formato reverso
            reverse_name = dns.reversename.from_address(ip)
            
            # Consultar PTR
            answers = dns.resolver.resolve(reverse_name, "PTR")
            
            ptr_records = [str(rdata) for rdata in answers]
            
            return {
                "ip": ip,
                "type": "PTR",
                "records": ptr_records,
                "count": len(ptr_records),
                "success": True
            }
            
        except ValueError:
            return {
                "error": f"'{ip}' no es una dirección IP válida",
                "ip": ip,
                "success": False
            }
        except dns.resolver.NXDOMAIN:
            return {
                "error": f"No se encontró registro PTR para '{ip}'",
                "ip": ip,
                "success": False
            }
        except dns.resolver.NoAnswer:
            return {
                "error": f"No hay registro PTR para '{ip}'",
                "ip": ip,
                "success": False
            }
        except Exception as e:
            return {
                "error": f"Error en búsqueda inversa: {str(e)}",
                "ip": ip,
                "success": False
            }
    
    def format_result(self, result: Dict[str, Any]) -> str:
        """
        Formatea un resultado DNS a texto legible.
        
        Args:
            result: Resultado de query, get_all_records o reverse_lookup
        
        Returns:
            Texto formateado del resultado
        """
        if not isinstance(result, dict):
            return str(result)
        
        # Manejar errores
        if "error" in result:
            return f"Error DNS: {result['error']}"
        
        # Formatear get_all_records (cuando records es un diccionario de tipos)
        if "records" in result and isinstance(result.get("records"), dict):
            domain = result.get("domain", "N/A")
            md = [f"### 📇 Registros DNS: {domain}", ""]
            
            records_dict = result["records"]
            priority_order = ["A", "AAAA", "MX", "NS", "CNAME", "TXT", "PTR"]
            
            # Descripciones amigables
            type_names = {
                "A": "🌐 IPv4",
                "AAAA": "🌐 IPv6",
                "MX": "📧 Servidores de Correo",
                "NS": "🔧 Servidores de Nombres",
                "CNAME": "🔗 Alias",
                "TXT": "📝 Registros de Texto",
                "PTR": "🔄 Reverso"
            }
            
            found_any = False
            for r_type in priority_order:
                if r_type in records_dict and records_dict[r_type]:
                    found_any = True
                    recs = records_dict[r_type]
                    type_label = type_names.get(r_type, r_type)
                    md.append(f"**{type_label}**")
                    md.append("")
                    
                    if r_type == "MX":
                        # Tabla limpia para MX
                        md.append("| Prioridad | Servidor |")
                        md.append("| :---: | :--- |")
                        for r in recs:
                            if isinstance(r, dict):
                                prio = r.get('priority', '-')
                                exch = r.get('exchange', 'N/A')
                                md.append(f"| **{prio}** | **{exch}** |")
                            else:
                                md.append(f"| - | **{r}** |")
                    elif r_type == "TXT":
                        # TXT puede ser largo, usar blockquote sin backticks
                        for r in recs:
                            truncated = str(r)[:150] + ('...' if len(str(r)) > 150 else '')
                            md.append(f"> {truncated}")
                    elif r_type in ["A", "AAAA"]:
                        # Tabla para IPs cuando hay múltiples
                        if len(recs) > 1:
                            ip_label = "Dirección IPv4" if r_type == "A" else "Dirección IPv6"
                            md.append(f"| {ip_label} |")
                            md.append("| :--- |")
                            for r in recs:
                                md.append(f"| **{r}** |")
                        else:
                            # Una sola IP, mostrar simple
                            md.append(f"• **{recs[0]}**")
                    elif r_type == "NS":
                        # Tabla para servidores de nombres
                        if len(recs) > 1:
                            md.append("| Servidor de Nombres |")
                            md.append("| :--- |")
                            for r in recs:
                                md.append(f"| **{r}** |")
                        else:
                            # Un solo servidor, mostrar simple
                            md.append(f"• **{recs[0]}**")
                    else:
                        # Lista simple para otros tipos (CNAME, PTR, etc.)
                        for r in recs:
                            md.append(f"• **{r}**")
                    
                    md.append("")
            
            if not found_any:
                md.append("> *No se encontraron registros públicos para este dominio.*")
            
            return "\n".join(md)

        # Formatear get_all_records (Legacy text summary fallback)
        if "summary_text" in result:
            return result["summary_text"]
        
        # Formatear query simple (registros = lista)
        if "records" in result and "domain" in result:
            domain = result["domain"]
            record_type = result.get("type", "A")
            records = result["records"]
            
            md = [f"### 📇 Consulta DNS: {domain} ({record_type})"]
            
            descriptions = {
                "MX": "_Servidores de Correo_",
                "TXT": "_Información de Texto_",
                "NS": "_Servidores de Nombres_",
                "A": "_Dirección IPv4_",
                "AAAA": "_Dirección IPv6_",
                "CNAME": "_Alias Canónico_"
            }
            
            if record_type in descriptions:
                md.append(descriptions[record_type])
                md.append("")
            
            if not records:
                 md.append("**No se encontraron registros.**")
            else:
                if record_type == "MX":
                     md.append("| Prioridad | Servidor |")
                     md.append("| :---: | :--- |")
                     for record in records:
                        if isinstance(record, dict):
                            md.append(f"| **{record.get('priority', 'N/A')}** | **{record.get('exchange', 'N/A')}** |")
                        else:
                             md.append(f"| - | **{record}** |")
                
                else:
                    # Usar tablas para múltiples valores de A, AAAA, NS
                    if record_type in ["A", "AAAA"] and len(records) > 1:
                        ip_label = "Dirección IPv4" if record_type == "A" else "Dirección IPv6"
                        md.append(f"| {ip_label} |")
                        md.append("| :--- |")
                        for record in records:
                            md.append(f"| **{record}** |")
                    elif record_type == "NS" and len(records) > 1:
                        md.append("| Servidor de Nombres |")
                        md.append("| :--- |")
                        for record in records:
                            md.append(f"| **{record}** |")
                    else:
                        # Lista simple para un solo valor o tipos como CNAME, TXT
                        for record in records:
                            md.append(f"• **{record}**")

            return "\n".join(md)
        
        # Formatear comparación DNS
        if result.get("type") == "dns_comparison" and "comparison" in result:
            return result["comparison"]
        
        # Formatear get_domain_info
        if "summary_text" in result and "info" in result:
            return result["summary_text"]
        
        # Formatear check_spf
        if "has_spf" in result:
            domain = result.get("domain", "N/A")
            if result.get("has_spf"):
                spf = result.get("spf_record", "N/A")
                return f"SPF para {domain}: ✅ Configurado\nRegistro: {spf}"
            else:
                return f"SPF para {domain}: ❌ No configurado\n{result.get('message', '')}"
        
        # Formatear check_dmarc
        if "has_dmarc" in result:
            domain = result.get("domain", "N/A")
            if result.get("has_dmarc"):
                dmarc = result.get("dmarc_record", "N/A")
                return f"DMARC para {domain}: ✅ Configurado\nRegistro: {dmarc}"
            else:
                return f"DMARC para {domain}: ❌ No configurado\n{result.get('message', '')}"
        
        # Formatear reverse lookup
        if "ip" in result and "records" in result:
            ip = result["ip"]
            records = result["records"]
            lines = [f"Búsqueda inversa (PTR) para {ip}:"]
            for record in records:
                lines.append(f"  • {record}")
            return "\n".join(lines)
        
        # Fallback
        return str(result)

