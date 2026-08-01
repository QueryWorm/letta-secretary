import requests

def searxng_search(query: str) -> str:
    """
    Search the web for current information using a self-hosted SearxNG instance.

    Args:
        query (str): The search query.

    Returns:
        str: Formatted search results (title, url, snippet) for up to 5 top results.
    """
    resp = requests.get(
        "http://searxng:8080/search",
        params={"q": query, "format": "json"},
        timeout=10,
    )
    data = resp.json()
    results = data.get("results", [])[:5]

    if not results:
        return "No results found."

    formatted = []
    for r in results:
        formatted.append(f"Title: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('content')}\n")

    return "\n---\n".join(formatted)
