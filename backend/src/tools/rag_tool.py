"""
Specialized RAG tool to query Pipe's knowledge base.
Encapsulates hybrid search in Qdrant and response generation, without
including infrastructure logging responsibilities.
"""
import re
import asyncio
import concurrent.futures
from typing import Optional, List, Dict, Any
from ..settings import settings
from ..repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from ..utils.embeddings import embedding_for_text
from ..core.cache import cache_result
from ..agent.llm_client import LLMClient


class RAGTool:
    """
    RAG tool optimized with parallel hybrid search using asyncio.gather().
    
    OPTIMIZATION: Uses asyncio.gather() to execute dense and sparse searches in parallel,
    improving performance by reducing the total latency of searches.
    """
    
    # OPTIMIZATION: Pre-compile static prompts to avoid rebuilding them on each call
    RELEVANCE_CHECK_PROMPT_TEMPLATE = """
Analyze if the following question can be answered based on internal technical documentation, stored Wireshark capture analysis results, or Pipe's capabilities.

User Question: "{query_text}"

- CORE MISSION RELEVANCE: Mark as RELEVANT any question seeking technical guidance, procedural understanding, or explanation of network behaviors typical of Band Steering and Wireshark.
- MANDATORY RELEVANCE: "The test", "the analysis", "the guide", "the procedure", or asking "what should I use as a guide" ALWAYS refer to the Band Steering project documentation. Mark them as RELEVANT immediately.
- DOMAIN OVER KEYWORDS: Do not rely solely on specific words. If the intent is technical or related to interpreting network outcomes, it is RELEVANT.
- CONTEXTUAL CONTINUITY: If the question is a follow-up or relates to the core system functionalities (BTM, KVR, 802.11 standards), it is RELEVANT.

Respond ONLY with one word: "relevant" or "not_relevant".
"""


    
    COMPLEXITY_PROMPT_TEMPLATE = """
Analyze the following question and determine its complexity:

Question: "{query_text}"

Determine if it is:
1. "simple" - Direct question requiring a brief answer (e.g., "What is X?", "Which is Y?")
2. "moderate" - Question requiring an explanation with some details (e.g., "How does X work?", "Explain Y")
3. "complex" - Question requiring a detailed explanation, multiple aspects, OR a complete list of items (e.g., "Compare X and Y", "Explain all aspects of Z", "What are the OSI model layers?", "Mention all types of X", "List all layers", "What are all the...?").

IMPORTANT: If the question requires a COMPLETE LIST of items (e.g., "OSI model layers", "firewall types", "network protocols", "all layers", "what are the layers"), it MUST be marked as "complex" to ensure ALL items are included without omission.

Respond ONLY with one word: "simple", "moderate", or "complex".
"""
    
    BASE_PROMPT_TEMPLATE = """
You are an expert assistant in Wireshark capture analysis, WiFi networks, and Band Steering. Your goal is to help the user by answering their questions based on the technical documentation provided by Pipe.
Important: Any ambiguous data must be interpreted within the networking spectrum (e.g., association = 802.11 WiFi association).

RESPONSE INSTRUCTIONS:
1. **ABSOLUTE SOURCE OF TRUTH**: Use EXCLUSIVELY the information contained in the "DOCUMENT CONTEXT". The indexed documentation is the **guide for understanding Wireshark captures and their results** (Band Steering, technical criteria). If the data is not in the document, DO NOT invent it or use general networking knowledge.
2. **WIRESHARK CONTEXT**: All Band Steering analysis here is based on Wireshark. If the user asks about "the test" or "guidance", refer to the guide for understanding captures and results.
3. **EXPLANATORY STYLE**: Explain in a technical yet accessible manner. Prioritize BTM status codes and transition events mentioned in the text.
   - **Simple values**: Use `inline code` (single backtick) for IPs, domains, short commands, BTM codes, and paths. E.g., `Status Code 0`, `BTM Request`.
   - **DO NOT USE CODE BLOCKS** (```) for a single line or single value. Blocks are only for long scripts or extensive configurations.
   - **DO NOT USE TABLES** unless strictly necessary to compare many data points. For lists of values, use bulleted lists (• or -).
   - **CORRECT LISTS**: The bullet and text must be on the SAME LINE. Do not put the bullet alone on a line.
     * Good: • **Phase 1:** Requirements design.
     * Bad: •\n**Phase 1:** Requirements design.
   - **Avoid horizontal scroll**: Keep lines contained and use compact formats.
4. **DO NOT INVENT DATA**: If the document mentions 3 concepts or phases, explain those 3.
5. **HANDLING GAPS**: If information about Band Steering is not in the documents, state it gently, indicating it is not found in the current technical documentation.

{context_section}
DOCUMENT CONTEXT (guide for understanding Wireshark captures and their results):
{context}

Question: {query_text}

Generate a natural, helpful, and precise response. Remember: use `inline code` for technical values, NO large blocks, and well-formatted lists.
Response:
"""
    
    SYSTEM_MESSAGE = """You are an expert in Pipe Wireshark capture analysis, specializing in Band Steering and network protocols.

YOUR MISSION:
1. Respond ONLY based on the provided documentation: the **guide for understanding Wireshark captures and their results**.
2. All concepts must be interpreted from the perspective of capture analysis and the Pipe project.
3. If the information is not in the documentation, state: "I did not find this specific information in the guide for understanding captures and results, but based on the context of the test...".
4. FORBIDDEN: General networking explanations that do not contribute to Band Steering analysis.
5. MEMORY: Maintain the conversation thread to understand what the user refers to (e.g., if asking for "the difference", it refers to the difference between concepts explained previously in the capture guide context).
"""
    
    RELEVANCE_SYSTEM_MESSAGE = "You are a technical analyzer for Pipe. 'The test', 'the analysis', 'the guide', or 'guidance' ALWAYS refer to Wireshark capture analysis and Band Steering and must be marked as RELEVANT specifically."
    
    COMPLEXITY_SYSTEM_MESSAGE = "You are an analyzer determining question complexity."
    
    # Common keywords for sparse search
    KEYWORD_PATTERNS = {
        'wifi': ['wifi', 'wi-fi', 'wireless', '802.11', 'association', 'reassociation', 'asociación', 'reasociación', 'asosacion', 'reasosacion', 'asosiacion'],
        'band_steering': ['band steering', 'btm', 'bss transition', '802.11v', '802.11k', '802.11r', 'kvr', 'steering', 'transicion', 'transición'],
        'ethernet': ['ethernet', 'cable', 'rj45', 'lan'],
        'tcp': ['tcp', 'retransmisión', 'retransmission', 'window size'],
        'dns': ['dns', 'domain', 'lookup', 'mx', 'txt'],
        'ip': ['ip address', 'v4', 'v6', 'icmp', 'ping', 'traceroute'],
    }
    
    def __init__(self):
        self.qdrant_repo = get_qdrant_repository()
        self.llm_client = LLMClient()

    async def _query_without_cache(self, query_text: str, top_k: int = 8, conversation_context: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Internal method that performs the RAG query without using cache.
        """
        return await self._execute_query(query_text, top_k, conversation_context, metadata)

    async def _query_with_cache(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Internal method that performs the RAG query with cache.
        Only used when there is NO conversation context.
        """
        if conversation_context:
             # If there is context, we do not use cache and pass the session_id if it were available (it is not here by signature)
            return await self._query_without_cache(query_text, top_k, conversation_context, metadata)
        
        # Note: Cache ignores metadata
        return await self._execute_query_cached(query_text, top_k)
    
    @cache_result("rag", ttl=7200)
    async def _execute_query_cached(self, query_text: str, top_k: int = 12):
        return await self._execute_query(query_text, top_k, None)

    def query(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):

        """
        Performs a RAG query on indexed documents.
        
        Args:
            query_text: Query text
            top_k: Number of results to retrieve (increased to 12 for better coverage)
            conversation_context: Optional context of the previous conversation (last messages)
        
        Returns:
            Dict with 'answer' and 'hits'
        
        Note: If conversation_context is provided, cache will NOT be used to avoid
        returning responses from previous queries without context.
        
        Note: This method is synchronous but internally uses asyncio for parallelization.
        Correctly handles the case when an event loop is already running (FastAPI/LangGraph).
        """
        # Helper to execute async from synchronous function
        def _run_async(coro):
            """Executes a corroutine, handling the case when an event loop is already running."""
            try:
                # Try to get the current event loop (if it's running)
                loop = asyncio.get_running_loop()
                # If a loop is running, execute in a separate thread with its own loop
                # This avoids the error "RuntimeError: asyncio.run() cannot be called from a running event loop"
                def run_in_new_loop():
                    """Executes the corroutine in a new event loop in this thread."""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result()
            except RuntimeError:
                # No event loop running, use asyncio.run() normally
                return asyncio.run(coro)
        
        # If there is conversation context, do NOT use cache (avoid incorrect responses)
        if conversation_context:
            return _run_async(self._query_without_cache(query_text, top_k, conversation_context, metadata))
        else:
            # Without context, use normal cache (without session_id to share cache)
            # Note: Cache ignores metadata to not invalidate cache by different trace_id
            return _run_async(self._query_with_cache(query_text, top_k, None, metadata))

    def _extract_keywords(self, query_text: str) -> List[str]:
        """
        Extracts relevant keywords from the query for sparse search.
        OPTIMIZED: Now extracts significant words from the user query,
        not just from a predefined list, to improve matching of exact phrases.
        """
        query_lower = query_text.lower()
        keywords = []
        
        # 1. Search for predefined technical patterns (high priority)
        for pattern_key, pattern_list in self.KEYWORD_PATTERNS.items():
            if any(pattern in query_lower for pattern in pattern_list):
                keywords.extend(pattern_list)
        
        # 2. Extract nouns and significant terms from the query
        # Remove common words/stopwords (basic list in Spanish and English)
        stopwords = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'de', 'del', 'al', 'a', 'en', 
            'con', 'por', 'para', 'sin', 'sobre', 'que', 'cual', 'quien', 'como', 'donde', 'cuando', 
            'es', 'son', 'fue', 'fueron', 'tiene', 'tienen', 'hay', 'hacer', 'esta', 'este', 'ese', 'esa',
            'what', 'is', 'are', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'
        }
        
        # Clean simple non-alphanumeric characters
        clean_text = re.sub(r'[^\w\s]', '', query_lower)
        words = clean_text.split()
        
        for word in words:
            # Filter short words (<3 chars) and stopwords
            if len(word) >= 3 and word not in stopwords:
                # Avoid duplicates
                if word not in keywords:
                    keywords.append(word)
        
        return keywords
    
    async def _dense_search(self, query_text: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Performs dense (vector) search in Qdrant.
        OPTIMIZATION: Asynchronous method for parallel execution with asyncio.gather().
        """
        try:
            # Execute embedding and search in a separate thread (synchronous operations)
            def _sync_dense_search():
                query_vector = embedding_for_text(query_text)
                # Increase top_k to minimum 10 for better coverage
                search_top_k = max(top_k, 10)
                results = self.qdrant_repo.search(
                    query_vector=query_vector,
                    top_k=search_top_k
                )
                return results
            
            # Use asyncio.to_thread to execute synchronous operation without blocking
            hits = await asyncio.to_thread(_sync_dense_search)
            return hits
        except Exception as e:
            return []
    
    async def _sparse_search(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Performs sparse search (by keywords) in Qdrant.
        OPTIMIZATION: Asynchronous method for parallel execution with asyncio.gather().
        """
        if not keywords:
            return []
        
        try:
            # Execute sparse search in separate thread (synchronous operation)
            def _sync_sparse_search():
                from qdrant_client import QdrantClient
                # Normalize URL (remove port if HTTPS)
                qdrant_url = settings.qdrant_url
                if qdrant_url.startswith('https://') and ':6333' in qdrant_url:
                    qdrant_url = qdrant_url.replace(':6333', '')
                
                # Configure client with API key if available
                client_kwargs = {"url": qdrant_url, "prefer_grpc": False}
                if settings.qdrant_api_key:
                    client_kwargs["api_key"] = settings.qdrant_api_key
                
                direct_client = QdrantClient(**client_kwargs)
                
                # OPTIMIZATION: Limit scroll to fewer points if there are many keywords
                scroll_limit = min(500, 100 * len(keywords))
                scroll_result = direct_client.scroll(
                    collection_name="documents",
                    limit=scroll_limit
                )
                
                keyword_hits = []
                keywords_lower = [kw.lower() for kw in keywords]
                
                for point in scroll_result[0]:
                    text = point.payload.get("text", "").lower()
                    # OPTIMIZATION: Verify all keywords at once
                    if any(kw in text for kw in keywords_lower):
                        keyword_hits.append({
                            "id": point.id,
                            "score": 1.0,  # High score for direct matches
                            "payload": point.payload
                        })
                        # Limit results early for better performance
                        if len(keyword_hits) >= 10:
                            break
                
                return keyword_hits
            
            # Use asyncio.to_thread to execute synchronous operation without blocking
            keyword_hits = await asyncio.to_thread(_sync_sparse_search)
            return keyword_hits
        except Exception as e:
            return []
    
    def _has_keyword_match(self, hits: List[Dict[str, Any]], keywords: List[str]) -> bool:
        """
        Verify if any hit contains the keywords.
        OPTIMIZATION: Separate method for better readability and testing.
        """
        if not keywords or not hits:
            return False
        
        keywords_lower = [kw.lower() for kw in keywords]
        return any(
            any(kw in h["payload"].get("text", "").lower() for kw in keywords_lower)
            for h in hits
        )
    
    async def _execute_query(self, query_text: str, top_k: int = 12, conversation_context: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Internal method that executes the real RAG query.
        OPTIMIZATION: Parallel hybrid search (dense + sparse) using asyncio.gather().
        
        Args:
            query_text: Query text
            top_k: Number of results to retrieve
            conversation_context: Optional context of the previous conversation
            metadata: Optional metadata for observability
        
        Returns:
            Dict with 'answer' and 'hits'
        """
        # Basic validation
        if not query_text or not isinstance(query_text, str) or not query_text.strip():
            return {"answer": "The query cannot be empty.", "hits": 0, "contexts": []}
        
        try:
            # OPTIMIZATION: Refine the query using the conversation context to improve search
            # This "de-references" questions like "and what is the difference?" to something full technical
            search_query = query_text
            if conversation_context:
                try:
                    refinement_prompt = f"""
Transform the following "Short Question" into a "Complete Technical Query" aimed at resolving the technical reference based on the "Conversation Context".

THE FOCUS MUST BE EXCLUSIVELY ON: Band Steering, Wireshark capture analysis, BTM, 802.11 WiFi, and the Pipe project.

CONVERSATION CONTEXT (Previous history):
{conversation_context}

CURRENT SHORT QUESTION: "{query_text}"

INSTRUCTIONS:
1. If the user asks "what is the difference", identify which terms were compared in the history and generate a technical query like "Technical difference between [Term A] and [Term B] in the context of Band Steering and Wireshark".
2. If the user asks about "that" or "the test", relate it to the technical concepts in the conversation.
3. The result must be an optimal technical phrase for searching in network engineering manuals.
4. Respond ONLY with the refined technical query, without introductions.

Refined technical query:
"""
                    def _sync_refine():
                        # Use routing tier (Groq) for fast refinement
                        return self.llm_client.generate(
                            prompt=refinement_prompt,
                            system_message="You are a technical query refiner.",
                            model_tier="routing",
                            temperature=0.0,
                            max_tokens=60,
                            metadata={**(metadata or {}), "generation_name": "RAG Query Refinement"}
                        ).strip()
                    
                    refined = await asyncio.to_thread(_sync_refine)
                    if refined and len(refined) > 5:
                        search_query = refined
                except Exception as e:
                    pass

            # OPTIMIZATION: Extract keywords before searches
            keywords = self._extract_keywords(search_query)
            
            # OPTIMIZATION: Execute dense and sparse search in parallel using asyncio.gather()
            # This is more efficient than ThreadPoolExecutor for I/O operations
            tasks = [self._dense_search(search_query, top_k)]
            
            # Add sparse search only if there are keywords
            if keywords:
                tasks.append(self._sparse_search(keywords))
            
            # Execute both searches in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            hits = results[0] if not isinstance(results[0], Exception) else []
            keyword_hits = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else []
            
            # Handle exceptions
            if isinstance(results[0], Exception):
                pass
            if len(results) > 1 and isinstance(results[1], Exception):
                pass
            
            # Combine results only if there are keyword_hits and no match in dense hits
            if keyword_hits and not self._has_keyword_match(hits, keywords):
                # Prioritize keyword matches at the beginning
                hits = keyword_hits[:3] + hits
            elif keyword_hits:
                # If there is already a match, add some additional keyword hits
                hits = keyword_hits[:2] + hits

            if not hits:
                # Check if there are documents in the collection
                try:
                    collection_info = self.qdrant_repo.get_collection_info()
                    points_count = collection_info.get('points_count', 0) if isinstance(collection_info, dict) else 0
                    
                    if points_count == 0:
                        return {
                            "answer": "No documents available in the database. Please upload PDF files to serve as a guide for understanding Wireshark captures and their results (e.g., Band Steering manuals) so I can answer your questions.",
                            "hits": 0,
                            "contexts": [],
                            "source": "no_documents"
                        }
                    else:
                        # Try a broader search with higher top_k
                        try:
                            query_vector = embedding_for_text(query_text)
                            alternative_hits = self.qdrant_repo.search(query_vector=query_vector, top_k=20)
                            if alternative_hits:
                                hits = alternative_hits
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # If after alternative search there are still no hits, return message
                if not hits:
                    return {
                        "answer": "I did not find specific information about your question in the available guide for understanding captures and results. Please ensure your question is related to Wireshark capture analysis, Band Steering, or network protocols.",
                        "hits": 0,
                        "contexts": [],
                        "source": "no_hits"
                    }
        except Exception as e:
            # If Qdrant is not available or there is a connection error, return error
            error_msg = str(e)
            if "conexión" in error_msg.lower() or "connection" in error_msg.lower() or "10061" in error_msg:
                return {
                    "answer": "Could not connect to the document database. Please verify that Qdrant is running.",
                    "hits": 0,
                    "error": "qdrant_connection_error",
                    "contexts": []
                }
            else:
                return {
                    "answer": f"Error searching documents: {error_msg}",
                    "hits": 0,
                    "error": "rag_error",
                    "contexts": []
                }

        # OPTIMIZATION: Validate relevance and analyze complexity in parallel using asyncio.gather()
        # IMPORTANT: Relevance validation must consider conversation context
        async def check_relevance():
            """Verifies if the question is relevant to the topic."""
            try:
                # If there is conversation context, include it in the validation
                # This avoids follow-up questions being marked as non-relevant
                if conversation_context:
                    # Build prompt with context for better validation
                    relevance_prompt_with_context = f"""
Analyze if the following question is relevant for Pipe (Wireshark capture analysis and Band Steering).

PREVIOUS CONVERSATION CONTEXT:
{conversation_context}

User Question: "{query_text}"

CRITICAL INSTRUCTIONS:
- CORE DOMAIN: If the question is about "the test", "guidance", "results", or any technical network aspect mentioned in the manuals, it is RELEVANT.
- CONTINUITY: If the question is a follow-up to a network topic or the Pipe project, mark as RELEVANT.
- Do not be restrictive with words; if the user seeks technical or procedural help from the system, it is RELEVANT.

Respond ONLY with one word: "relevant" or "not_relevant".
"""
                    relevance_prompt = relevance_prompt_with_context
                else:
                    relevance_prompt = self.RELEVANCE_CHECK_PROMPT_TEMPLATE.format(query_text=query_text)
                
                # Execute call to OpenAI in separate thread (synchronous operation)
                def _sync_relevance_check():
                        # Use routing tier (Groq) for fast and cheap relevance check
                        return self.llm_client.generate(
                        prompt=relevance_prompt,
                        system_message=self.RELEVANCE_SYSTEM_MESSAGE,
                        model_tier="routing",
                        temperature=0.0,
                        max_tokens=10,
                        metadata={**(metadata or {}), "generation_name": "RAG Relevance Check"}
                    ).strip().lower()
                
                response_text = await asyncio.to_thread(_sync_relevance_check)
                is_relevant = "relevant" in response_text and "not_relevant" not in response_text
                return is_relevant
            except Exception as e:
                return True  # In case of error, allow response
        
        async def check_complexity():
            """Analyzes the complexity of the question."""
            try:
                complexity_prompt = self.COMPLEXITY_PROMPT_TEMPLATE.format(query_text=query_text)
                
                # Execute call to OpenAI in separate thread (synchronous operation)
                def _sync_complexity_check():
                    # Use routing tier (Groq) for complexity analysis
                    return self.llm_client.generate(
                        prompt=complexity_prompt,
                        system_message=self.COMPLEXITY_SYSTEM_MESSAGE,
                        model_tier="routing",
                        temperature=0.0,
                        max_tokens=10,
                        metadata={**(metadata or {}), "generation_name": "RAG Complexity Check"}
                    ).strip().lower()
                
                complexity = await asyncio.to_thread(_sync_complexity_check)
                return complexity
            except Exception as e:
                return "moderate"
        
        # OPTIMIZATION: Execute relevance and complexity validation in parallel using asyncio.gather()
        is_relevant, complexity = await asyncio.gather(
            check_relevance(),
            check_complexity(),
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(is_relevant, Exception):
            is_relevant = True
        if isinstance(complexity, Exception):
            complexity = "moderate"
        
        # If not relevant, return message indicating it cannot answer
        if not is_relevant:
            return {
                "answer": "I'm sorry, my knowledge is limited to the guide for understanding Wireshark captures and their results (Band Steering, Pipe). Your question seems to be outside of this specialized scope.",
                "hits": 0,
                "contexts": [],
                "source": "out_of_topic"
            }
        
        # Filter and concatenate most relevant chunks
        # IMPORTANT: Use a lower threshold (0.25) to include more relevant results and increase coverage
        relevant_hits = [h for h in hits if h.get('score', 0) > 0.25]
        
        # If there are no hits with score > 0.25, use top 5 results (even with low scores)
        if not relevant_hits:
            relevant_hits = hits[:5] if hits else []
        else:
            # Limit to maximum 6 most relevant chunks for better coverage (formerly 3)
            relevant_hits = relevant_hits[:6]
        
        # Concatenate the most relevant texts
        context = "\n\n".join([h["payload"].get("text", "") for h in relevant_hits])
        
        # OPTIMIZATION: Limit context size to avoid memory and latency issues
        MAX_CONTEXT_LENGTH = 5500  # Reduced from 7000 to improve speed and avoid timeouts
        if len(context) > MAX_CONTEXT_LENGTH:
            # Truncate context keeping the first most relevant chunks
            context = context[:MAX_CONTEXT_LENGTH]
        
        # If context is empty after filtering, return error
        if not context or not context.strip():
            return {
                "answer": "I did not find specific information about your question in the available guide for understanding captures and results. Please ensure your question is related to Wireshark capture analysis, Band Steering, or network protocols.",
                "hits": len(hits),
                "contexts": [],
                "source": "empty_context"
            }

        # Build prompt with conversation context if available
        # Conversation context can contain previous actions, results, and events
        context_section = ""
        if conversation_context:
            context_section = f"""
PREVIOUS CONVERSATION CONTEXT:
{conversation_context}

INSTRUCTIONS ON CONVERSATION CONTEXT:
1. If the question makes direct reference to actions, results, or events mentioned in the conversation context (e.g., "the ping you did", "before the ping", "the previous result", "to which domain was it"), USE that information from the conversation context to answer.
2. If the question is a FOLLOW-UP to something mentioned in the context (e.g., "what are the types?", "explain more", "mention others", "what else is there"), and the context mentions a networking/telecommunications topic, then:
   - USE the CONVERSATION CONTEXT to understand what the question refers to
   - SEARCH in the DOCUMENTS for information related to that context topic
   - COMBINE both sources: use the context to understand the reference and the documents for the technical information
3. If the question is about technical concepts, definitions, or educational information WITHOUT reference to the context, use EXCLUSIVELY the DOCUMENTS.
4. If the question specifically asks about something that happened in the previous conversation (domains, IPs, operation results), the conversation context is the MAIN source of information.
5. For general technical information (what is it, how does it work, definitions), the DOCUMENTS are the ONLY source of information. DO NOT add general knowledge.

FOLLOW-UP EXAMPLES:
- Context: "Firewalls are security devices..."
- Question: "What are the types?"
- Response: Search documents for "firewall types" and answer based on documents.

- Context: "I pinged google.com and got..."
- Question: "Which domain was it?"
- Response: Use the conversation context (google.com).
"""

        # Determine target length based on complexity (already obtained in parallel)
        # INCREASED: Higher limits to ensure complete answers, especially for lists
        if "simple" in complexity:
            length_guidance = "BRIEF and DIRECT response: 2-4 sentences (50-100 words). Get straight to the point without long explanations."
            max_tokens_response = 200  # Increased from 100 to 200
        elif "complex" in complexity:
            length_guidance = "COMPLETE and DETAILED response: 200-400 words with structured explanation, relevant examples, and clear organization. If the question requires a complete list (e.g., all OSI layers, all types of something), ensure ALL items in the list are included without omission."
            max_tokens_response = 800  # Optimized for speed (formerly 1200)
        else:  # moderate
            length_guidance = "BALANCED response: 100-200 words with clear explanation and some relevant details. If the question requires a list, include all important items."
            max_tokens_response = 500  # Increased from 300 to 500
        
        # OPTIMIZATION: Use pre-compiled template to build prompt
        prompt = self.BASE_PROMPT_TEMPLATE.format(
            length_guidance=length_guidance,
            context_section=context_section,
            context=context,
            query_text=query_text
        )
        
        # Select model according to complexity
        # OPTIMIZATION: Use "cheap" (Groq) by default to save Gemini quota
        # Only use Gemini ("standard") if explicitly "complex"
        selected_tier = "cheap"
        if "complex" in complexity:
            selected_tier = "standard"

        # Execute call to OpenAI in separate thread (blocking synchronous operation)
        def _sync_generate_answer():
            """Generates the response using the configured provider (Gemini/OpenAI)."""
            # Use standard tier for main generation
            return self.llm_client.generate(
                prompt=prompt,
                system_message=self.SYSTEM_MESSAGE,
                model_tier=selected_tier,  # Use dynamic tier based on complexity
                temperature=0.1,
                max_tokens=max_tokens_response,
                metadata={**(metadata or {}), "generation_name": "RAG Final Generation"}
            ).strip()
        
        # Use asyncio.to_thread to execute blocking operation without blocking event loop
        answer = await asyncio.to_thread(_sync_generate_answer)
        
        # General post-generation validation: verify that key statements are supported by context
        # This is a general validation system that works for any type of question
        context_lower = context.lower()
        answer_lower = answer.lower()
        
        # Extract key phrases from the response (simple approximation)
        # Split the response into sentences and verify that main concepts are in the context
        sentences = re.split(r'[.!?]\s+', answer)
        
        potential_hallucinations = []
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Extract important keywords (proper nouns, technologies, technical concepts)
            # Words that are probably technical concepts (uppercase, acronyms, etc.)
            words = re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', sentence)
            tech_patterns = re.findall(r'\b[a-z]+(?:\s+[a-z]+)*\b', sentence.lower())
            
            # Verify if the sentence mentions concepts that are not in the context
            sentence_lower = sentence.lower()
            # If the sentence is very specific and has no context keywords, it might be hallucinated
            # But this is a simple heuristic - not perfect
            
            # List of common technologies/concepts that tend to be hallucinated (for logging)
            common_hallucination_keywords = {
                "frame relay", "atm", "asynchronous transfer mode", "sd-wan", 
                "software-defined wan", "dsl", "digital subscriber line", "adsl",
                "cable modem", "ftth", "fiber to the home"
            }
            
            for keyword in common_hallucination_keywords:
                if keyword in sentence_lower and keyword not in context_lower:
                    potential_hallucinations.append(f"'{keyword}' mentioned but not in context")
        
        # Return response with contexts for evaluation (if needed)
        # The contexts can be used for evaluation with Ragas
        contexts_list = [h["payload"].get("text", "") for h in hits[:10] if h.get("payload", {}).get("text")]  # First 10 chunks
        
        
        result = {
            "answer": answer,
            "hits": len(hits),
            # Include contexts for evaluation (first chunks as list)
            "contexts": contexts_list
        }
        
        return result



# Test