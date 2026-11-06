"""Anthropic and OpenAI wrappers, plus pure functions that pull URLs out of responses.

Sources come from structured API fields, never from the model describing its own browsing.
The extract_* functions take plain dicts (response.model_dump()) so they can be
unit-tested against saved samples without calling any API.
"""
import re
import time

SOURCES_RE = re.compile(r"^\s*\**SOURCES\**\s*:\**\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def dedupe(seq):
    seen, out = set(), []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_self_reported(text):
    """Text after the last 'SOURCES:' line, or None."""
    matches = SOURCES_RE.findall(text or "")
    return matches[-1].strip() if matches else None


# ---------- Anthropic ----------

def extract_anthropic(content):
    """content = list of response content blocks as dicts."""
    queries, result_urls, cited_urls, texts, errors = [], [], [], [], []
    for block in content:
        btype = block.get("type")
        if btype == "server_tool_use" and block.get("name") == "web_search":
            q = (block.get("input") or {}).get("query")
            if q:
                queries.append(q)
        elif btype == "web_search_tool_result":
            payload = block.get("content")
            if isinstance(payload, list):
                result_urls += [r.get("url") for r in payload if r.get("type") == "web_search_result"]
            elif isinstance(payload, dict):  # error object, returned with HTTP 200
                errors.append(payload.get("error_code") or "web_search_error")
        elif btype == "text":
            texts.append(block.get("text", ""))
            for c in block.get("citations") or []:
                if c.get("type") == "web_search_result_location":
                    cited_urls.append(c.get("url"))
    text = "".join(texts)
    return {
        "search_queries": queries,
        "result_urls": dedupe(result_urls),
        "cited_urls": dedupe(cited_urls),
        "response_text": text,
        "self_reported_sources": parse_self_reported(text),
        "search_errors": errors,
    }


def call_anthropic(client, prompt, settings):
    cfg = settings["anthropic"]
    tool = {
        "type": cfg["tool_type"],
        "name": "web_search",
        "max_uses": cfg["max_uses"],
        "user_location": settings["user_location"],
    }
    messages = [{"role": "user", "content": prompt}]
    content, input_tokens, output_tokens, searches = [], 0, 0, 0
    for _ in range(settings["max_pause_continues"] + 1):
        resp = client.messages.create(
            model=cfg["model"], max_tokens=cfg["max_tokens"], tools=[tool],
            messages=messages, timeout=settings["call_timeout_s"],
        )
        data = resp.model_dump(mode="json", exclude_none=True)
        content += data["content"]
        usage = data.get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        searches += (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
        if data.get("stop_reason") != "pause_turn":
            break
        # Long turn paused by the API: send the assistant message back unchanged to continue.
        messages = [messages[0], {"role": "assistant", "content": data["content"]}]
    out = extract_anthropic(content)
    out.update(input_tokens=input_tokens, output_tokens=output_tokens,
               web_search_requests=searches, raw=content)
    return out


# ---------- OpenAI ----------

def extract_openai(output):
    """output = response.output items as dicts."""
    queries, result_urls, cited_urls, texts = [], [], [], []
    for item in output:
        itype = item.get("type")
        if itype == "web_search_call":
            action = item.get("action") or {}
            if action.get("type") == "search":
                if action.get("query"):
                    queries.append(action["query"])
                queries += action.get("queries") or []
            for src in action.get("sources") or []:
                url = src.get("url") if isinstance(src, dict) else None
                if url:
                    result_urls.append(url)
        elif itype == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                    for ann in part.get("annotations") or []:
                        if ann.get("type") == "url_citation":
                            cited_urls.append(ann.get("url"))
    text = "".join(texts)
    return {
        "search_queries": dedupe(queries),
        "result_urls": dedupe(result_urls),
        "cited_urls": dedupe(cited_urls),
        "response_text": text,
        "self_reported_sources": parse_self_reported(text),
        "search_errors": [],
    }


def call_openai(client, prompt, settings):
    cfg = settings["openai"]
    tool = {"type": "web_search", "search_context_size": cfg.get("search_context_size", "medium"),
            "user_location": settings["user_location"]}
    kwargs = dict(model=cfg["model"], tools=[tool], input=prompt,
                  include=["web_search_call.action.sources"],
                  timeout=settings["call_timeout_s"])
    if cfg.get("reasoning_effort"):
        kwargs["reasoning"] = {"effort": cfg["reasoning_effort"]}
    resp = client.responses.create(**kwargs)
    data = resp.model_dump(mode="json", exclude_none=True)
    out = extract_openai(data.get("output", []))
    usage = data.get("usage", {})
    out.update(input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
               web_search_requests=sum(1 for i in data.get("output", []) if i.get("type") == "web_search_call"),
               raw=data)
    return out


# ---------- shared ----------

def with_retries(fn, retries, base_delay=2.0):
    """Call fn(); on exception retry with exponential backoff. Re-raises the last error."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(base_delay * (2 ** attempt))


def make_clients(providers, env):
    """Create SDK clients lazily from env vars. Never prints keys."""
    clients = {}
    if "anthropic" in providers:
        import anthropic
        clients["anthropic"] = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=0)
    if "openai" in providers:
        import openai
        clients["openai"] = openai.OpenAI(api_key=env["OPENAI_API_KEY"], max_retries=0)
    return clients


CALLERS = {"anthropic": call_anthropic, "openai": call_openai}
