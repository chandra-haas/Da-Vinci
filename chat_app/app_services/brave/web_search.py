import requests
from django.conf import settings

def brave_web_search(query, top_n=3):
    print(f"[DEBUG] [web_search] Query: {query}")
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": top_n,
    }
    url = "https://api.search.brave.com/res/v1/web/search"
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"[DEBUG] [web_search] HTTP Status: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        results = data.get("web", {}).get("results", [])
        print(f"[DEBUG] [web_search] Raw results: {results}")
        formatted = [
            {"description": item.get("description", ""), "url": item.get("url", "")}
            for item in results if item.get("description")
        ]
        print(f"[DEBUG] [web_search] Formatted results: {formatted}")
        return formatted
    except Exception as e:
        print(f"[DEBUG] [web_search] Error: {e}")
        return []

def format_search_results_for_gpt(results):
    print(f"[DEBUG] [web_search] Formatting {len(results)} results for GPT")
    formatted = "\n".join(
        f"{item['description']} {item['url']}".strip() for item in results
    )
    print(f"[DEBUG] [web_search] Formatted string for GPT:\n{formatted}")
    return formatted