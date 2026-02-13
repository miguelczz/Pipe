"""
Helper functions for agent nodes.
Centralizes common logic and eliminates duplication, without managing logging.
"""
import re
from typing import Optional, List, Tuple
from ..agent.llm_client import LLMClient

llm = LLMClient()


def detect_operation_type(step: str, prompt: str, conversation_context: Optional[str] = None) -> str:
    """
    Detects the operation type using heuristics first, LLM only if necessary.
    OPTIMIZATION: Uses fast heuristic analysis before calling the LLM.
    
    Args:
        step: Plan step
        prompt: Original user question
        conversation_context: Optional context from previous conversation
    
    Returns:
        "ping", "traceroute", "compare", or "default"
    """
    # OPTIMIZATION: First try fast heuristics (without LLM)
    step_lower = (step or "").lower()
    prompt_lower = (prompt or "").lower()
    context_lower = (conversation_context or "").lower()
    
    combined_text = f"{step_lower} {prompt_lower} {context_lower}"
    
    # Detect comparison (most specific first)
    # Include variations of compare verb and common patterns
    compare_keywords = [
        "compare", "comparison", "differences", "contrast", "vs", "versus",
        # Patterns indicating comparison between two elements
        "ping from", "ping of", "latency of"  # When mentioned with "with" or "and"
    ]
    
    # Detect comparison patterns (e.g., "ping of X with Y", "X vs Y")
    has_compare_keyword = any(keyword in combined_text for keyword in compare_keywords)
    has_comparison_pattern = (
        (" with " in combined_text or " and " in combined_text) and 
        (combined_text.count(".com") >= 2 or combined_text.count(".") >= 4)  # Multiple domains
    )
    
    if has_compare_keyword and has_comparison_pattern:
        return "compare"
    
    # Also detect if there are explicit comparison keywords
    if any(keyword in combined_text for keyword in ["compare", "comparison", "vs", "versus", "differences"]):
        return "compare"
    
    # Detect traceroute
    if any(keyword in combined_text for keyword in ["traceroute", "trace route", "trace-route", "network route"]):
        return "traceroute"
    
    # Detect ping (most common, check after traceroute)
    if any(keyword in combined_text for keyword in ["ping", "latency", "response time"]):
        return "ping"
    
    # If cannot determine with heuristics, use LLM (only when necessary)
    try:
        context_section = f"\nPrevious conversation context:\n{conversation_context}" if conversation_context else ""
        
        analysis_prompt = f"""
Analyze the following request and determine what type of network operation needs to be performed.

Plan step: "{step}"
Original question: "{prompt}"
{context_section}

Available operation types:
- "ping": Measure latency/response time to a host or domain
- "traceroute": Trace the network path to a host or domain
- "compare": Compare two or more hosts/domains/IPs (comparative analysis)
- "default": Other unspecified network operation

Respond ONLY with one word: "ping", "traceroute", "compare", or "default"
"""
        response = llm.generate(analysis_prompt, max_tokens=50).strip().lower()
        
        # Extract operation type from response
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
    Extracts a domain from text using regex.
    
    Returns:
        Domain found or None
    """
    domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
    match = re.search(domain_pattern, text)
    return match.group(0) if match else None


def extract_ip_from_text(text: str) -> Optional[str]:
    """
    Extracts an IP from text using regex.
    
    Returns:
        IP found or None
    """
    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    match = re.search(ip_pattern, text)
    return match.group(0) if match else None


def extract_domains_from_text(text: str) -> List[str]:
    """
    Extracts all domains from text using regex first, and LLM as fallback.
    
    Returns:
        List of domains found
    """
    # First look for explicit domains with regex
    domain_pattern = r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"
    explicit_domains = re.findall(domain_pattern, text)
    
    # If explicit domains found, return them
    if explicit_domains:
        return list(dict.fromkeys(explicit_domains))  # Remove duplicates maintaining order
    
    # If no explicit domains found, use LLM to identify services/domains
    # This allows the agent to identify services mentioned by name (Google, Facebook, etc.)
    llm_domains = extract_domains_using_llm(text)
    
    # Combine and remove duplicates
    all_domains = explicit_domains + llm_domains
    return list(dict.fromkeys(all_domains))  # Remove duplicates maintaining order


def extract_domain_using_llm(text: str) -> Optional[str]:
    """
    Extracts a domain from text using LLM as fallback.
    Useful when regex doesn't find explicit domains.
    
    Returns:
        Domain found or None
    """
    try:
        prompt = f"""
From the following text, identify the domain name or service mentioned (such as Instagram, Facebook, Google, etc.).
Respond ONLY with the found domain name, without explanations or additional text.
If you don't find a domain name, respond "none".

Text: "{text}"
"""
        response = llm.generate(prompt).strip().lower()
        
        if response and response != "none":
            words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9-]*\b', response)
            if words:
                domain_name = words[0]
                if len(domain_name) > 2:
                    return f"{domain_name}.com"
        return None
    except Exception as e:
        return None


# List of known common services for fast conversion
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
    Extracts multiple domains from text using LLM intelligently.
    The LLM identifies services mentioned by name and converts them to full domains.
    
    First checks if it's a known service (faster), then uses LLM as fallback.
    
    Returns:
        List of domains found (format: example.com)
    """
    # First check if it's a known service (faster and more reliable)
    text_lower = text.lower()
    found_domains = []
    
    for service, domain in COMMON_SERVICES.items():
        if service in text_lower:
            # Verify it's not part of another word
            import re
            pattern = r'\b' + re.escape(service) + r'\b'
            if re.search(pattern, text_lower):
                if domain not in found_domains:
                    found_domains.append(domain)
    
    if found_domains:
        return found_domains
    
    # If no known services found, use LLM
    try:
        prompt = f"""
Analyze the following text and identify ALL mentioned services, companies, or domains.

INSTRUCTIONS:
1. Identify services mentioned by name (e.g., "Google", "Facebook", "Amazon") or by full domain (e.g., "google.com")
2. For each identified service, convert the name to the corresponding full domain (e.g., "Google" → "google.com", "Gmail" → "gmail.com")
3. If it is already a full domain, use it as is
4. Respond ONLY with the full domains, one per line, in format: example.com
5. Do not include explanations, bullet points, or additional text
6. If you don't find any service or domain, respond "none"

Conversion examples:
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

Text to analyze: "{text}"

Respond with full domains (one per line):
"""
        response = llm.generate(prompt, max_tokens=200).strip()
        
        if not response or response.lower() == "none":
            return []
        
        domains = []
        for line in response.split('\n'):
            line = line.strip()
            # Clean line of special characters and spaces
            line = re.sub(r'[^\w\.-]', '', line)
            
            if line and len(line) > 3:
                # Verify it has domain format (contains dot and extension)
                if '.' in line and len(line.split('.')) >= 2:
                    # Verify it's not just an extension
                    parts = line.split('.')
                    if len(parts[0]) > 1:  # Domain name must have at least 2 characters
                        domain = line.lower()
                        # Ensure it ends with valid extension
                        if re.match(r'^[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(\.[a-zA-Z]{2,})?$', domain):
                            if domain not in domains:
                                domains.append(domain)
        
        return domains
    except Exception as e:
        return []


def extract_hosts_from_text(text: str, validate_func) -> List[str]:
    """
    Extracts hosts (IPs or domains) from text intelligently.
    Uses regex first, then LLM to identify services mentioned by name.
    
    Args:
        text: Text to analyze
        validate_func: Function to validate if a token is a valid host
    
    Returns:
        List of found hosts (without duplicates)
    """
    # Extract explicit IPs and domains from text
    hosts = [p for p in text.split() if validate_func(p)]
    
    # Extract domains (this already uses LLM internally if no explicit domains found)
    domain_matches = extract_domains_from_text(text)
    
    # Combine and remove duplicates
    for domain in domain_matches:
        if domain not in hosts and validate_func(domain):
            hosts.append(domain)
    
    return list(dict.fromkeys(hosts))  # Remove duplicates maintaining order


def detect_dns_operation_type(step: str, prompt: str) -> Tuple[str, bool]:
    """
    Detects DNS operation type using LLM to understand real intent.
    Does not depend on keywords, but analyzes meaning.
    
    Returns:
        Tuple (operation_type, is_all_records)
        operation_type: "reverse", "compare", "spf", "dmarc", "domain_info", "all", or specific type ("A", "MX", etc.)
        is_all_records: True if all records should be obtained
    """
    try:
        analysis_prompt = f"""
Analyze the following request and determine what type of DNS operation needs to be performed.

Plan step: "{step}"
Original question: "{prompt}"

Available DNS operation types:
- "reverse": Reverse DNS lookup (PTR) - get domain from an IP
- "compare": Compare DNS records between two or more domains
- "spf": Verify SPF configuration of a domain
- "dmarc": Verify DMARC configuration of a domain
- "domain_info": Get complete domain information (IPs, email, security, etc.)
- "all": Get ALL DNS records of a domain (A, AAAA, MX, TXT, NS, CNAME)
- Specific types: "A", "AAAA", "MX", "TXT", "NS", "CNAME" - when a specific type is requested

INSTRUCTIONS:
1. Analyze the real INTENT, not just keywords
2. If it mentions "all", "complete", "all records" without specifying type → ("A", True)
3. If it mentions a specific type (MX, TXT, NS, etc.) → (type, False)
4. If it mentions comparing domains → ("compare", False)
5. If it mentions SPF or verify SPF → ("spf", False)
6. If it mentions DMARC or verify DMARC → ("dmarc", False)
7. If it mentions complete information, summary, or domain info → ("domain_info", False)
8. If it mentions reverse lookup, PTR, or getting domain from IP → ("reverse", False)

Examples:
- "View DNS records for google.com" → ("A", True) - all records
- "MX for gmail.com" → ("MX", False) - only MX
- "Compare DNS for google and facebook" → ("compare", False)
- "Verify SPF for gmail.com" → ("spf", False)
- "Complete information for google.com" → ("domain_info", False)

Respond ONLY with the operation type in format: "type,is_all"
Where type is one of: reverse, compare, spf, dmarc, domain_info, all, A, AAAA, MX, TXT, NS, CNAME
And is_all is: true or false

Example response: "A,true" or "MX,false" or "compare,false"
"""
        response = llm.generate(analysis_prompt, max_tokens=100).strip().lower()
        
        # Parse response
        if "," in response:
            parts = response.split(",")
            op_type = parts[0].strip()
            is_all = "true" in parts[1].strip() if len(parts) > 1 else False
        else:
            # If not in expected format, try to extract
            op_type = response.strip()
            is_all = "all" in op_type or "complete" in op_type
        
        # Normalize types
        if op_type in ["reverse", "ptr"]:
            return ("reverse", False)
        elif op_type in ["compare"]:
            return ("compare", False)
        elif op_type in ["spf"]:
            return ("spf", False)
        elif op_type in ["dmarc"]:
            return ("dmarc", False)
        elif op_type in ["domain_info", "domain info", "info", "complete info", "summary"]:
            return ("domain_info", False)
        elif op_type in ["all", "complete"] or is_all:
            return ("A", True)
        elif op_type.upper() in ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]:
            return (op_type.upper(), False)
        else:
            # Default: all records
            return ("A", True)
    except Exception as e:
        # Simple fallback in case of error
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
        if "all" in step_lower or "complete" in prompt_lower:
            return ("A", True)
        return ("A", True)  # Default: all records

