import httpx

# Category lists mapping categories to the exact tool names defined in server.py
TOOL_CATEGORIES = {
    "notes": [
        "list_notes",
        "search_resources",
        "get_resource",
        "create_note",
        "update_note",
    ],
    "files": [
        "search_files",
        "get_file_info",
        "read_file_info",
        "send_file",
    ],
    "sandbox": [
        "write_file",
        "run_local_command",
        "create_local_directory",
        "list_local_files",
        "read_local_file",
        "patch_local_file",
        "grep_local_files",
        "zip_sandbox_workspace",
    ],
    "web": [
        "search_web",
        "fetch_url",
    ],
    "github": [
        "search_github",
        "list_github_prs",
        "create_github_pr",
    ],
}

# Substring matches for category mapping
CATEGORY_KEYWORDS = {
    "notes":   ["note", "notes", "remember", "jot down", "resource", "reminder"],
    "files":   ["file", "files", "document", "pdf", "resume", "attachment",
                "upload", "send me", "download"],
    "sandbox": ["script", "run this", "execute", "sandbox", "grep",
                "zip", "local command", "generate a", "write a file",
                "create a file"],
    "web":     ["search the web", "google", "look up", "website",
                "http", "https", "fetch", "scrape"],
    "github":  ["github", "pr", "pull request", "repo", "repository",
                "commit", "branch", "issue"],
}

def classify_by_keywords(user_message: str) -> set[str]:
    """Lowercase the message and return the set of categories whose keyword list has a word-boundary match."""
    msg = user_message.lower()
    matched = set()
    import re
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, msg):
                matched.add(category)
                break  # match found for this category, check next category
    return matched

async def classify_by_llm(user_message: str) -> set[str] | None:
    """Use Ollama Qwen model directly without tools to classify ambiguous messages."""
    from mcp_pocketing.ai_client import _get_ollama_settings
    url, model = _get_ollama_settings()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Classify the user's message into exactly one word: chat, notes, files, sandbox, web, or github. Reply with only that word, nothing else."
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "think": False,
        "options": {
            "num_predict": 5
        },
        "stream": False
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=None)
            response.raise_for_status()
            data = response.json()
            reply = data.get("message", {}).get("content", "").strip().lower()
            reply = reply.strip(".,!?;:\"'")
            
            if reply == "chat":
                return set()
            elif reply in TOOL_CATEGORIES:
                return {reply}
            
            # Unrecognized response
            return None
    except Exception as e:
        # Fall back to None sentinel to indicate failure
        try:
            from pocketing_logging.logger import get_ai_logger
            get_ai_logger().warning(f"Ollama tool routing classification failed: {e}")
        except Exception:
            pass
        return None

def build_filtered_tools(mcp_tools, categories: set[str]) -> list:
    """Filter MCP tools down to those in selected categories, and convert to Ollama schema."""
    if not categories:
        return []
        
    allowed_names = set()
    for cat in categories:
        if cat in TOOL_CATEGORIES:
            allowed_names.update(TOOL_CATEGORIES[cat])
            
    filtered = [tool for tool in mcp_tools if tool.name in allowed_names]
    
    from mcp_pocketing.ai_client import convert_mcp_tools_to_ollama
    return convert_mcp_tools_to_ollama(filtered)

async def route(user_message: str, mcp_tools) -> list:
    """Top-level entry point to route the tools list based on message classification."""
    categories = classify_by_keywords(user_message)
    method = "keywords"
    if not categories:
        llm_result = await classify_by_llm(user_message)
        if llm_result is None:
            # classification failed, safe fallback to full tools list
            from mcp_pocketing.ai_client import convert_mcp_tools_to_ollama
            full_tools = convert_mcp_tools_to_ollama(mcp_tools)
            try:
                from pocketing_logging.logger import get_ai_logger
                ai_log = get_ai_logger()
                ai_log.info("TOOL ROUTER DECISION")
                ai_log.info("  Method:     fallback (failed)")
                ai_log.info(f"  Tools sent: {len(full_tools)} (full set)")
            except Exception:
                pass
            return full_tools
        categories = llm_result
        method = "llm"
        
    filtered_tools = build_filtered_tools(mcp_tools, categories)
    try:
        from pocketing_logging.logger import get_ai_logger
        ai_log = get_ai_logger()
        ai_log.info("TOOL ROUTER DECISION")
        ai_log.info(f"  Method:     {method}")
        ai_log.info(f"  Categories: {list(categories) if categories else 'none (chat)'}")
        ai_log.info(f"  Tools sent: {len(filtered_tools)}")
    except Exception:
        pass
        
    return filtered_tools
