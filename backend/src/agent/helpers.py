"""
Funciones helper para los nodos del agente.
Centraliza lógica común y elimina duplicación.
"""
import re
import logging
from typing import Optional, List, Tuple
from ..agent.llm_client import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient()


def detect_operation_type(step: str, prompt: str, conversation_context: Optional[str] = None) -> str:
    """
    Detecta el tipo de operación usando heurística primero, LLM solo si es necesario.
    OPTIMIZACIÓN: Usa análisis heurístico rápido antes de llamar al LLM.
    
    Args:
        step: Paso del plan
        prompt: Pregunta original del usuario
        conversation_context: Contexto opcional de la conversación previa
    
    Returns:
        "ping", "traceroute", "compare", o "default"
    """
    # OPTIMIZACIÓN: Primero intentar heurística rápida (sin LLM)
    step_lower = (step or "").lower()
    prompt_lower = (prompt or "").lower()
    context_lower = (conversation_context or "").lower()
    
    combined_text = f"{step_lower} {prompt_lower} {context_lower}"
    
    # Detectar comparación (más específico primero)
    # Incluir variaciones del verbo comparar y patrones comunes
    compare_keywords = [
        "compare", "compara", "comparar", "comparando", "comparison", "comparación",
        "diferencias", "differences", "contrast", "contraste",
        "vs", "versus", "frente a",
        # Patrones que indican comparación entre dos elementos
        "ping de", "latencia de"  # Cuando se menciona junto con "con" o "y"
    ]
    
    # Detectar patrones de comparación (ej: "ping de X con Y", "X vs Y")
    has_compare_keyword = any(keyword in combined_text for keyword in compare_keywords)
    has_comparison_pattern = (
        (" con " in combined_text or " y " in combined_text) and 
        (combined_text.count(".com") >= 2 or combined_text.count(".") >= 4)  # Múltiples dominios
    )
    
    if has_compare_keyword and has_comparison_pattern:
        return "compare"
    
    # También detectar si hay palabras clave explícitas de comparación
    if any(keyword in combined_text for keyword in ["compare", "compara", "comparar", "comparando", "comparison", "comparación", "vs", "versus", "diferencias", "differences"]):
        return "compare"
    
    # Detectar traceroute
    if any(keyword in combined_text for keyword in ["traceroute", "trace route", "trace-route", "trazar ruta", "ruta de red"]):
        return "traceroute"
    
    # Detectar ping (más común, verificar después de traceroute)
    if any(keyword in combined_text for keyword in ["ping", "latencia", "latency", "tiempo de respuesta", "response time"]):
        return "ping"
    
    # Si no se puede determinar con heurística, usar LLM (solo cuando es necesario)
    try:
        context_section = f"\nContexto de conversación previa:\n{conversation_context}" if conversation_context else ""
        
        analysis_prompt = f"""
Analiza la siguiente solicitud y determina qué tipo de operación de red se necesita realizar.

Paso del plan: "{step}"
Pregunta original: "{prompt}"
{context_section}

Tipos de operación disponibles:
    pass
- "ping": Medir latencia/tiempo de respuesta a un host o dominio
- "traceroute": Trazar la ruta de red hasta un host o dominio
- "compare": Comparar dos o más hosts/dominios/IPs (análisis comparativo)
- "default": Otra operación de red no especificada

Responde SOLO con una palabra: "ping", "traceroute", "compare", o "default"
"""
        response = llm.generate(analysis_prompt, max_tokens=50).strip().lower()
        
        # Extraer el tipo de operación de la respuesta
        if "compare" in response or "compar" in response:
            return "compare"
        elif "traceroute" in response or "trace" in response:
            return "traceroute"
        elif "ping" in response:
            return "ping"
        else:
            return "default"
    except Exception as e:
        return "default"


def extract_domain_from_text(text: str) -> Optional[str]:
    """
    Extrae un dominio del texto usando regex.
    
    Returns:
        Dominio encontrado o None
    """
    domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
    match = re.search(domain_pattern, text)
    return match.group(0) if match else None


def extract_ip_from_text(text: str) -> Optional[str]:
    """
    Extrae una IP del texto usando regex.
    
    Returns:
        IP encontrada o None
    """
    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    match = re.search(ip_pattern, text)
    return match.group(0) if match else None


def extract_domains_from_text(text: str) -> List[str]:
    """
    Extrae todos los dominios del texto usando regex primero, y LLM como fallback.
    
    Returns:
        Lista de dominios encontrados
    """
    # Primero buscar dominios explícitos con regex
    domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
    explicit_domains = re.findall(domain_pattern, text)
    
    # Si encontramos dominios explícitos, retornarlos
    if explicit_domains:
        return list(dict.fromkeys(explicit_domains))  # Eliminar duplicados manteniendo orden
    
    # Si no encontramos dominios explícitos, usar LLM para identificar servicios/dominios
    # Esto permite que el agente identifique servicios mencionados por nombre (Google, Facebook, etc.)
    llm_domains = extract_domains_using_llm(text)
    
    # Combinar y eliminar duplicados
    all_domains = explicit_domains + llm_domains
    return list(dict.fromkeys(all_domains))  # Eliminar duplicados manteniendo orden


def extract_domain_using_llm(text: str) -> Optional[str]:
    """
    Extrae un dominio del texto usando LLM como fallback.
    Útil cuando el regex no encuentra dominios explícitos.
    
    Returns:
        Dominio encontrado o None
    """
    try:
        prompt = f"""
        Del siguiente texto, identifica el nombre de dominio o servicio mencionado (como Instagram, Facebook, Google, etc.).
        Responde SOLO con el nombre del dominio encontrado, sin explicaciones ni texto adicional.
        Si no encuentras un nombre de dominio, responde "ninguno".
        
        Texto: "{text}"
        """
        response = llm.generate(prompt).strip().lower()
        
        if response and response != "ninguno":
            words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9-]*\b', response)
            if words:
                domain_name = words[0]
                if len(domain_name) > 2:
                    return f"{domain_name}.com"
        return None
    except Exception as e:
        return None


# Lista de servicios comunes conocidos para conversión rápida
COMMON_SERVICES = {
    "facebook": "facebook.com",
    "google": "google.com",
    "instagram": "instagram.com",
    "twitter": "twitter.com",
    "x": "x.com",
    "youtube": "youtube.com",
    "amazon": "amazon.com",
    "microsoft": "microsoft.com",
    "netflix": "netflix.com",
    "gmail": "gmail.com",
    "outlook": "outlook.com",
    "github": "github.com",
    "linkedin": "linkedin.com",
    "reddit": "reddit.com",
    "whatsapp": "whatsapp.com",
    "telegram": "telegram.org",
    "discord": "discord.com",
    "openai": "openai.com",
    "cloudflare": "cloudflare.com",
    "aws": "amazonaws.com",
}


def extract_domains_using_llm(text: str) -> List[str]:
    """
    Extrae múltiples dominios del texto usando LLM de manera inteligente.
    El LLM identifica servicios mencionados por nombre y los convierte a dominios completos.
    
    Primero verifica si es un servicio conocido (más rápido), luego usa LLM como fallback.
    
    Returns:
        Lista de dominios encontrados (formato: ejemplo.com)
    """
    # Primero verificar si es un servicio conocido (más rápido y confiable)
    text_lower = text.lower()
    found_domains = []
    
    for service, domain in COMMON_SERVICES.items():
        if service in text_lower:
            # Verificar que no sea parte de otra palabra
            import re
            pattern = r'\b' + re.escape(service) + r'\b'
            if re.search(pattern, text_lower):
                if domain not in found_domains:
                    found_domains.append(domain)
    
    if found_domains:
        return found_domains
    
    # Si no se encontraron servicios conocidos, usar LLM
    try:
        prompt = f"""
Analiza el siguiente texto e identifica TODOS los servicios, empresas o dominios mencionados.

INSTRUCCIONES:
    pass
1. Identifica servicios mencionados por nombre (ej: "Google", "Facebook", "Amazon") o por dominio completo (ej: "google.com")
2. Para cada servicio identificado, convierte el nombre al dominio completo correspondiente (ej: "Google" → "google.com", "Gmail" → "gmail.com")
3. Si ya es un dominio completo, úsalo tal cual
4. Responde SOLO con los dominios completos, uno por línea, en formato: ejemplo.com
5. No incluyas explicaciones, puntos, ni texto adicional
6. Si no encuentras ningún servicio o dominio, responde "ninguno"

Ejemplos de conversión:
    pass
- "Google" → google.com
- "Facebook" → facebook.com
- "Amazon AWS" → amazonaws.com
- "Microsoft" → microsoft.com
- "Netflix" → netflix.com
- "Gmail" → gmail.com
- "Outlook" → outlook.com
- "GitHub" → github.com
- "Instagram" → instagram.com
- "YouTube" → youtube.com

Texto a analizar: "{text}"

Responde con los dominios completos (uno por línea):
    pass
"""
        response = llm.generate(prompt, max_tokens=200).strip()
        
        if not response or response.lower() == "ninguno":
            return []
        
        domains = []
        for line in response.split('\n'):
            line = line.strip()
            # Limpiar la línea de caracteres especiales y espacios
            line = re.sub(r'[^\w\.-]', '', line)
            
            if line and len(line) > 3:
                # Verificar que tenga formato de dominio (contiene punto y extensión)
                if '.' in line and len(line.split('.')) >= 2:
                    # Verificar que no sea solo una extensión
                    parts = line.split('.')
                    if len(parts[0]) > 1:  # El nombre del dominio debe tener al menos 2 caracteres
                        domain = line.lower()
                        # Asegurar que termine con extensión válida
                        if re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(\.[a-zA-Z]{2,})?$', domain):
                            if domain not in domains:
                                domains.append(domain)
        
        return domains
    except Exception as e:
        return []


def extract_hosts_from_text(text: str, validate_func) -> List[str]:
    """
    Extrae hosts (IPs o dominios) del texto de manera inteligente.
    Usa regex primero, luego LLM para identificar servicios mencionados por nombre.
    
    Args:
        text: Texto a analizar
        validate_func: Función para validar si un token es un host válido
    
    Returns:
        Lista de hosts encontrados (sin duplicados)
    """
    # Extraer IPs y dominios explícitos del texto
    hosts = [p for p in text.split() if validate_func(p)]
    
    # Extraer dominios (esto ya usa LLM internamente si no encuentra dominios explícitos)
    domain_matches = extract_domains_from_text(text)
    
    # Combinar y eliminar duplicados
    for domain in domain_matches:
        if domain not in hosts and validate_func(domain):
            hosts.append(domain)
    
    return list(dict.fromkeys(hosts))  # Eliminar duplicados manteniendo orden


def detect_dns_operation_type(step: str, prompt: str) -> Tuple[str, bool]:
    """
    Detecta el tipo de operación DNS usando LLM para entender la intención real.
    No depende de palabras clave, sino que analiza el significado.
    
    Returns:
        Tupla (operation_type, is_all_records)
        operation_type: "reverse", "compare", "spf", "dmarc", "domain_info", "all", o tipo específico ("A", "MX", etc.)
        is_all_records: True si se deben obtener todos los registros
    """
    try:
        analysis_prompt = f"""
Analiza la siguiente solicitud y determina qué tipo de operación DNS se necesita realizar.

Paso del plan: "{step}"
Pregunta original: "{prompt}"

Tipos de operación DNS disponibles:
    pass
- "reverse": Búsqueda inversa DNS (PTR) - obtener dominio desde una IP
- "compare": Comparar registros DNS entre dos o más dominios
- "spf": Verificar configuración SPF de un dominio
- "dmarc": Verificar configuración DMARC de un dominio
- "domain_info": Obtener información completa del dominio (IPs, email, seguridad, etc.)
- "all": Obtener TODOS los registros DNS de un dominio (A, AAAA, MX, TXT, NS, CNAME)
- Tipos específicos: "A", "AAAA", "MX", "TXT", "NS", "CNAME" - cuando se solicita un tipo específico

INSTRUCCIONES:
    pass
1. Analiza la INTENCIÓN real, no solo palabras clave
2. Si menciona "todos", "all", "completo", "todos los registros" sin especificar tipo → ("A", True)
3. Si menciona un tipo específico (MX, TXT, NS, etc.) → (tipo, False)
4. Si menciona comparar dominios → ("compare", False)
5. Si menciona SPF o verificar SPF → ("spf", False)
6. Si menciona DMARC o verificar DMARC → ("dmarc", False)
7. Si menciona información completa, resumen, o info del dominio → ("domain_info", False)
8. Si menciona búsqueda inversa, PTR, o obtener dominio de IP → ("reverse", False)

Ejemplos:
    pass
- "Consulta los registros DNS de google.com" → ("A", True) - todos los registros
- "MX de gmail.com" → ("MX", False) - solo MX
- "Compara DNS de google y facebook" → ("compare", False)
- "Verifica SPF de gmail.com" → ("spf", False)
- "Información completa de google.com" → ("domain_info", False)

Responde SOLO con el tipo de operación en formato: "tipo,is_all"
Donde tipo es uno de: reverse, compare, spf, dmarc, domain_info, all, A, AAAA, MX, TXT, NS, CNAME
Y is_all es: true o false

Ejemplo de respuesta: "A,true" o "MX,false" o "compare,false"
"""
        response = llm.generate(analysis_prompt, max_tokens=100).strip().lower()
        
        # Parsear respuesta
        if "," in response:
            parts = response.split(",")
            op_type = parts[0].strip()
            is_all = "true" in parts[1].strip() if len(parts) > 1 else False
        else:
            # Si no tiene formato esperado, intentar extraer
            op_type = response.strip()
            is_all = "all" in op_type or "todos" in op_type or "completo" in op_type
        
        # Normalizar tipos
        if op_type in ["reverse", "ptr", "inversa"]:
            return ("reverse", False)
        elif op_type in ["compare", "comparar"]:
            return ("compare", False)
        elif op_type in ["spf"]:
            return ("spf", False)
        elif op_type in ["dmarc"]:
            return ("dmarc", False)
        elif op_type in ["domain_info", "domain info", "info", "información completa", "resumen"]:
            return ("domain_info", False)
        elif op_type in ["all", "todos", "completo"] or is_all:
            return ("A", True)
        elif op_type.upper() in ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]:
            return (op_type.upper(), False)
        else:
            # Por defecto: todos los registros
            return ("A", True)
    except Exception as e:
        # Fallback simple solo en caso de error
        step_lower = (step or "").lower()
        prompt_lower = prompt.lower()
        if "reverse" in step_lower or "ptr" in step_lower or "reverse" in prompt_lower:
            return ("reverse", False)
        if "compare" in step_lower or "comparar" in step_lower:
            return ("compare", False)
        if "spf" in prompt_lower:
            return ("spf", False)
        if "dmarc" in prompt_lower:
            return ("dmarc", False)
        if "all" in step_lower or "todos" in step_lower or "completo" in prompt_lower:
            return ("A", True)
        return ("A", True)  # Por defecto: todos los registros

