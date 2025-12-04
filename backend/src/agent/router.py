import re
import json
import logging
from openai import OpenAI
from ..settings import settings
from ..tools.rag_tool import RAGTool
from ..tools.ip_tool import IPTool
from ..tools.dns_tool import DNSTool
from ..models.schemas import AgentState
from ..core.cache import cache_result

# Logger específico para este módulo
logger = logging.getLogger(__name__)

# Cliente moderno de OpenAI
client = OpenAI(api_key=settings.openai_api_key)


class NetMindAgent:
    def __init__(self):
        self.rag = RAGTool()
        self.iptool = IPTool()
        self.dnstool = DNSTool()
        self.llm_model = settings.llm_model
        self.client = client  # Cliente de OpenAI para validaciones

    def decide(self, user_input: str, state: AgentState) -> dict:
        """
        Decide qué herramienta usar según la intención del usuario.
        Primero valida que la pregunta esté relacionada con redes y telecomunicaciones.
        OPTIMIZACIÓN: Resultados cacheados por 5 minutos para consultas similares.
        """
        # Extraer contexto relevante para el caché (solo últimos 5 mensajes como string serializable)
        context_for_cache = ""
        context_messages_str = ""
        if state.context_window and len(state.context_window) > 0:
            # Últimos 3 mensajes para contexto corto
            context_messages = state.context_window[:-1][-3:] if len(state.context_window) > 1 else state.context_window[-3:]
            if context_messages:
                context_parts = []
                for msg in context_messages:
                    role = msg.role if hasattr(msg, 'role') else 'user'
                    content = msg.content if hasattr(msg, 'content') else str(msg)
                    context_parts.append(f"{role}: {content[:150]}")
                context_for_cache = "\n".join(context_parts)
            
            # Últimos 5 mensajes para el prompt completo
            last_5_messages = state.context_window[-5:]
            context_messages_str = "\n".join([f"{m.role if hasattr(m, 'role') else 'user'}: {m.content if hasattr(m, 'content') else str(m)}" for m in last_5_messages])
        
        # Usar función interna con caché (solo strings serializables)
        return self._decide_cached(user_input, context_for_cache, context_messages_str)
    
    @cache_result("router_decision", ttl=300)  # Cache por 5 minutos
    def _decide_cached(self, user_input: str, context_text: str, context_messages_str: str) -> dict:
        """
        Función interna con caché. Solo recibe strings serializables para evitar errores de serialización.
        """
        # Obtener contexto de conversación previa para entender referencias
        if context_text:
            context_text = "\n\nContexto de conversación previa:\n" + context_text
        
        # OPTIMIZACIÓN: Combinar validación de relevancia y decisión de herramienta en una sola llamada
        # Esto reduce de 2 llamadas a 1, ahorrando ~2-4 segundos
        combined_prompt = f"""
You are NetMind, a smart agent that decides which internal tool to use for a user's request.

STEP 1: First, determine if the question is relevant to networks, telecommunications, network protocols, or network technologies.
STEP 2: If relevant, decide which tool to use and create a plan.

{context_text}

User request: \"\"\"{user_input}\"\"\"
Context (last 5 messages):
{context_messages_str}

RELEVANCE RULES (STEP 1):
- ONLY mark as relevant if the question is CLEARLY and DIRECTLY related to networks, network protocols, telecommunications, or network technologies
- If the question references previous network operations mentioned in context (ping, traceroute, DNS, IP analysis, etc.), it is RELEVANT even if it doesn't explicitly mention networks
- Questions about general physics, mathematics, history, literature, medicine, cooking, sports, etc. are NOT RELEVANT (unless they directly reference previous network operations)
- Only relevant: network protocols (TCP/IP, HTTP, DNS, etc.), network devices (routers, switches, etc.), network technologies (WiFi, Ethernet, etc.), network operations (ping, traceroute, etc.), network configuration, network security, etc.

TOOL DECISION RULES (STEP 2 - only if relevant):
1. ANALYZE THE USER REQUEST CAREFULLY: Break down the request into separate parts if it contains multiple questions or tasks.
2. IMPORTANT: If the user is asking for a follow-up, conclusion, or continuation of a previous conversation (e.g., "conclusión", "resumen", "entonces", "en resumen", "dame más detalles sobre lo anterior"), use RAG tool but be aware it should use conversation context.
3. UNDERSTAND USER INTENTION FROM CONTEXT: When the user makes a request like "haz uno", "hazlo", "ejecuta uno", "realiza uno", "haz un", "ejecuta un", you must understand what they want to do by analyzing:
   - The conversation context: What was discussed in previous messages? What operation or concept was mentioned?
   - The user's intent: What specific action are they asking to perform?
   - The relationship between context and request: If they asked "¿Qué es DNS?" and then say "realiza uno", they likely want to perform a DNS operation. If they asked "¿Qué es un ping?" and then say "realiza uno", they likely want to perform a ping operation.
   
   You must intelligently infer the user's intention from the full context, not from keywords alone. Analyze what operation makes sense given the conversation flow.
   
   Examples of intelligent context understanding:
   - Context: "user: ¿Qué es DNS?" → User: "Realiza uno a google" → tool: "dns", plan_step: "query all DNS records for google.com"
   - Context: "user: ¿Qué es un ping?" → User: "Haz uno a facebook" → tool: "ip", plan_step: "ping to facebook.com"
   - Context: "user: Explica cómo funciona traceroute" → User: "Hazlo a google" → tool: "ip", plan_step: "traceroute to google.com"
   
   The key is understanding the user's intent from the conversation flow, not matching keywords.

4. For each part, determine which tool is needed by understanding the user's intent:
   - RAG tool: for questions about concepts, definitions, explanations, educational content, asking "what is", "que es", "explain", "define", follow-up questions, conclusions, summaries
   - IP tool: for network operations like ping, traceroute, IP comparison, IP validation, comparing domains/IPs, network analysis
   - DNS tool: for DNS queries, domain records (A, AAAA, MX, TXT, NS, CNAME), reverse DNS lookup, DNS comparison, SPF/DMARC verification, domain information
   
   IMPORTANT DNS DECISION LOGIC:
   - If user asks for DNS records WITHOUT explicitly mentioning a specific type (A, MX, NS, TXT, etc.), the plan step should indicate "query all DNS records" or "get all DNS records"
   - Only use a specific DNS record type query when the user EXPLICITLY mentions that type (e.g., "MX de", "registros NS", "TXT records")
   - For DNS comparison: if user asks to "comparar DNS", "compare DNS", use plan step: "compare DNS records between [domain1] and [domain2]"
   - For SPF verification: if user asks "verificar SPF", "check SPF", use plan step: "check SPF for [domain]"
   - For DMARC verification: if user asks "verificar DMARC", "check DMARC", use plan step: "check DMARC for [domain]"
   - For complete domain info: if user asks "información del dominio", "info del dominio", use plan step: "get domain info for [domain]"

5. Generate plan_steps that are SPECIFIC and CLEAR. Each step should:
   - Be a single, executable action
   - Clearly indicate what information or operation is needed
   - Include relevant details (domains, IPs, concepts) mentioned in the user request
   - Be self-contained so the agent can determine which tool to use

6. IMPORTANT: If the user asks multiple things requiring different tools, create MULTIPLE steps:
   - Example: "Que es un ping? y compara IPs de facebook y google" 
     → plan_steps: ["retrieve information about what ping is", "compare IP addresses of facebook.com and google.com"]

7. For single questions, use ONE step:
   - "Que es un ping?" → ["retrieve information about what ping is"]
   - "Compara IPs de facebook y google" → ["compare IP addresses of facebook.com and google.com"]

8. NEVER use vague steps like "ensure clarity", "elaborate explanation", "improve response" - these are not executable actions

9. Each step should be specific enough that the agent can automatically determine which tool (RAG, IP, or DNS) to use

10. The "tool" field should be the PRIMARY tool if multiple are needed, or the only tool if one is needed.

OUTPUT FORMAT:
Respond with a valid JSON containing these keys:
- is_relevant: true if the question is relevant to networks/telecommunications, false otherwise
- tool: one of ["rag", "ip", "dns", "none"] (use "none" if not relevant)
- reason: short explanation why you chose this tool (or why it's not relevant)
- plan_steps: list of short, concrete, actionable steps (empty if not relevant)
- rejection_message: (only if not relevant) a friendly message explaining why the question is out of scope

Respond ONLY in JSON format. No extra text or markdown.
"""

        try:
            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are NetMind, a smart router that validates relevance and decides which tool to use. Always respond with valid JSON."},
                    {"role": "user", "content": combined_prompt}
                ],
                max_tokens=500,
            )

            text = response.choices[0].message.content.strip()

            # Limpieza de delimitadores Markdown
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()

            # Extraer JSON del texto
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                text = match.group(0)

            logger.info(f"Texto limpiado para parsear: {text}")

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(
                    "No se pudo parsear el JSON. Se usará 'none'.")
                data = {"is_relevant": False, "tool": "none", "reason": "parse_fail", "plan_steps": [], "rejection_message": "Error al procesar la solicitud."}

        except Exception as e:
            data = {"is_relevant": False, "tool": "none",
                    "reason": f"llm_error: {str(e)}", "plan_steps": [], "rejection_message": "Error al procesar la solicitud."}

        # Verificar relevancia
        is_relevant = data.get("is_relevant", True)  # Por defecto, asumir relevante si no se especifica
        
        # Si NO es relevante, retornar inmediatamente
        if not is_relevant:
            rejection_msg = data.get("rejection_message", "Lo siento, solo puedo responder preguntas relacionadas con redes, telecomunicaciones, protocolos de red y tecnologías de red. Tu pregunta parece estar fuera de esta temática.")
            logger.info(f"[Router] Pregunta rechazada por estar fuera de tema: '{user_input}'")
            return {
                "tool": "none",
                "reason": "out_of_topic",
                "plan_steps": [],
                "rejection_message": rejection_msg
            }

        tool = data.get("tool", "").lower().strip()
        reason = data.get("reason", "").lower()
        plan = data.get("plan_steps", [])
        
        # Validar y normalizar plan_steps
        if not plan or len(plan) == 0:
            # Si no hay plan_steps pero hay una herramienta seleccionada, generar uno por defecto
            if tool == "rag":
                plan = [f"retrieve information about {user_input[:50]}"]
            elif tool == "ip":
                if "compare" in user_input.lower():
                    plan = ["compare IPs"]
                elif any(k in user_input.lower() for k in ["trace", "traceroute", "route"]):
                    plan = ["traceroute to host"]
                else:
                    plan = ["execute ip tool"]
            else:
                plan = []
        
        # Filtrar solo pasos vagos o no ejecutables que el LLM pueda haber generado
        # Estos pasos causan iteraciones innecesarias, pero NO forzamos decisiones
        vague_keywords = ["ensure", "elaborate", "clarify", "improve", "enhance", "refine", "polish"]
        plan = [step for step in plan if not any(keyword in step.lower() for keyword in vague_keywords)]
        
        # Solo generar pasos por defecto si el LLM no generó ninguno (caso edge)
        if not plan and tool in ["rag", "ip"]:
            if tool == "rag":
                plan = [f"retrieve information about {user_input[:50]}"]
            elif tool == "ip":
                plan = ["execute ip tool"]
        
        # Solo validar que el tool sea válido, no forzar su valor basándonos en palabras clave
        # Confiamos en la decisión del LLM
        if tool not in ["ip", "rag", "dns", "none"]:
            # Solo corregir si el tool es completamente inválido, usar "none" como fallback
            data["tool"] = "none"
        
        # Asegurar que plan_steps esté en el resultado final
        data["plan_steps"] = plan

        logger.info(f"Decision final normalizada: {data}")
        logger.info(f"Plan steps generados: {plan}")
        return data

    def handle(self, user_input: str, state: AgentState) -> dict:
        """
        Ejecuta la herramienta correspondiente según la decisión del modelo.
        Usa el estado de sesión proporcionado (AgentState) para mantener el contexto.
        """
        decision = self.decide(user_input, state)
        tool = decision.get("tool")
        plan_steps = decision.get("plan_steps", [])

        # Validación: si se selecciona una herramienta pero plan_steps está vacío
        if tool in ["rag", "ip", "dns"] and not plan_steps:
            logger.warning(f"Tool '{tool}' seleccionada pero plan_steps está vacío. Usando tool basado en user_input.")
            # Intentar inferir plan_steps desde el input si es posible
            if tool == "ip":
                if any(self.iptool.validate_ip_or_domain(part) for part in user_input.split()):
                    plan_steps = ["execute ip tool"]
                elif "compare" in user_input.lower():
                    plan_steps = ["compare ips"]
                elif any(k in user_input.lower() for k in ["trace", "traceroute", "route"]):
                    plan_steps = ["traceroute to host"]
            elif tool == "rag":
                plan_steps = ["query documents"]
            elif tool == "dns":
                plan_steps = ["query DNS records"]

        if tool == "rag":
            # Extraer contexto de conversación de los últimos mensajes (excluyendo el actual)
            conversation_context = None
            if state.context_window and len(state.context_window) > 1:
                # Obtener los últimos 5 mensajes anteriores al actual (para contexto)
                context_messages = state.context_window[:-1][-5:]  # Excluir el último (que es el actual)
                if context_messages:
                    # Formatear contexto como string
                    context_parts = []
                    for msg in context_messages:
                        role = msg.role if hasattr(msg, 'role') else 'user'
                        content = msg.content if hasattr(msg, 'content') else str(msg)
                        context_parts.append(f"{role}: {content}")
                    conversation_context = "\n".join(context_parts)
                    logger.info(f"Usando contexto de conversación ({len(context_messages)} mensajes) para RAG")
            
            # Pasar el contexto al RAG tool (si hay contexto, NO usará cache)
            out = self.rag.query(user_input, conversation_context=conversation_context)
            # Actualizar el estado de sesión en lugar del global
            state.add_message("system", f"User: {user_input}\nRAG: {out.get('answer', 'No answer')}")
            logger.info(f"RAGTool ejecutada. Resultado: {out}")
            return {"tool": "rag", "result": out, "decision": decision}

        elif tool == "ip":
            # --- TRACEROUTE ---
            if any("trace" in s.lower() for s in plan_steps):
                # Extraer IP o dominio válido del texto
                hosts = [part for part in user_input.split(
                ) if self.iptool.validate_ip_or_domain(part)]
                if hosts:
                    host = hosts[0]
                    out = self.iptool.tracert(host)
                else:
                    # Intentar extraer un dominio de forma más flexible
                    domain_match = re.search(
                        r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                    if domain_match:
                        host = domain_match.group(0)
                        out = self.iptool.tracert(host)
                    else:
                        out = {"error": "no_valid_host_found"}

            # --- COMPARACIÓN DE IPs ---
            elif any("compare" in s.lower() for s in plan_steps):
                parts = [p for p in re.split(
                    r"[\s,]+", user_input) if self.iptool.validate_ip(p)]
                if len(parts) >= 2:
                    out = self.iptool.compare(parts[0], parts[1])
                else:
                    out = {"error": "no_two_ips_found"}

            else:
                out = {
                    "note": "ip tool called, but no clear plan step matched", "plan": plan_steps}

            # Actualizar el estado de sesión en lugar del global
            state.add_message("system", f"User: {user_input}\nIPTool: {out}")
            logger.info(f"IPTool ejecutada. Resultado: {out}")
            return {"tool": "ip", "result": out, "decision": decision}

        elif tool == "dns":
            # Detectar tipo de consulta DNS basándose en plan_steps (más inteligente)
            user_lower = user_input.lower()
            plan_lower = " ".join(plan_steps).lower() if plan_steps else ""
            
            # Verificar si el plan indica "all records" o "todos los registros"
            is_all_records_request = (
                "all dns records" in plan_lower or
                "all records" in plan_lower or
                "todos los registros" in plan_lower or
                "query all" in plan_lower or
                "get all" in plan_lower
            )
            
            # Detectar comparación DNS
            is_comparison = (
                "compare" in plan_lower or
                "comparar" in plan_lower or
                "comparison" in plan_lower or
                "comparar dns" in user_lower or
                "comparar registros" in user_lower
            )
            
            # Detectar verificaciones específicas
            is_spf_check = "spf" in user_lower and ("verificar" in user_lower or "check" in user_lower or "tiene" in user_lower)
            is_dmarc_check = "dmarc" in user_lower and ("verificar" in user_lower or "check" in user_lower or "tiene" in user_lower)
            is_domain_info = any(keyword in user_lower for keyword in [
                "información del dominio", "info del dominio", "domain info",
                "información completa", "resumen del dominio"
            ])
            
            # Búsqueda inversa (PTR)
            if "reverse" in user_lower or "ptr" in user_lower or "inversa" in user_lower:
                # Extraer IP del texto
                ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
                ip_match = re.search(ip_pattern, user_input)
                if ip_match:
                    ip = ip_match.group(0)
                    out = self.dnstool.reverse_lookup(ip)
                else:
                    out = {"error": "no_valid_ip_found_for_reverse_lookup"}
            
            # Comparación DNS
            elif is_comparison:
                # Extraer dos dominios
                domains = re.findall(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if len(domains) >= 2:
                    out = self.dnstool.compare_dns(domains[0], domains[1])
                else:
                    out = {"error": "Se necesitan al menos 2 dominios para comparar. Ejemplo: 'compara DNS de google.com con facebook.com'"}
            
            # Verificación SPF
            elif is_spf_check:
                domain_match = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if domain_match:
                    domain = domain_match.group(0)
                    out = self.dnstool.check_spf(domain)
                else:
                    out = {"error": "No se encontró un dominio válido para verificar SPF"}
            
            # Verificación DMARC
            elif is_dmarc_check:
                domain_match = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if domain_match:
                    domain = domain_match.group(0)
                    out = self.dnstool.check_dmarc(domain)
                else:
                    out = {"error": "No se encontró un dominio válido para verificar DMARC"}
            
            # Información completa del dominio
            elif is_domain_info:
                domain_match = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if domain_match:
                    domain = domain_match.group(0)
                    out = self.dnstool.get_domain_info(domain)
                else:
                    out = {"error": "No se encontró un dominio válido"}
            
            # Consulta de todos los registros
            # Confiar completamente en la decisión del LLM a través de plan_steps
            elif is_all_records_request:
                # Extraer dominio
                domain_match = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if domain_match:
                    domain = domain_match.group(0)
                    out = self.dnstool.get_all_records(domain)
                else:
                    out = {"error": "no_valid_domain_found"}
            
            # Consulta específica de tipo de registro
            # El LLM debe indicar en plan_steps qué tipo de registro consultar
            else:
                # Intentar extraer el tipo de registro del plan_steps
                record_type = "A"  # Por defecto
                
                # Buscar en plan_steps primero (decisión del LLM)
                if plan_steps:
                    plan_text = " ".join(plan_steps).lower()
                    if re.search(r'\bmx\b', plan_text):
                        record_type = "MX"
                    elif re.search(r'\btxt\b', plan_text):
                        record_type = "TXT"
                    elif re.search(r'\bns\b', plan_text) or "nameserver" in plan_text:
                        record_type = "NS"
                    elif re.search(r'\bcname\b', plan_text):
                        record_type = "CNAME"
                    elif re.search(r'\baaaa\b', plan_text) or "ipv6" in plan_text:
                        record_type = "AAAA"
                
                # Extraer dominio
                domain_match = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", user_input)
                if domain_match:
                    domain = domain_match.group(0)
                    out = self.dnstool.query(domain, record_type)
                else:
                    out = {"error": "no_valid_domain_found"}
            
            # Actualizar el estado de sesión
            state.add_message("system", f"User: {user_input}\nDNSTool: {out}")
            logger.info(f"DNSTool ejecutada. Resultado: {out}")
            return {"tool": "dns", "result": out, "decision": decision}

        else:
            # Actualizar el estado de sesión en lugar del global
            state.add_message("system", f"User: {user_input}\nSystem: no action taken.")
            logger.info(f"Ninguna tool seleccionada para '{user_input}'")
            return {"tool": "none", "result": None, "decision": decision}
