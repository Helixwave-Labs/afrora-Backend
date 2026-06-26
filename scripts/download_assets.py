import os
import urllib.request
import ssl

ssl._create_default_https_context = ssl._create_unverified_context

assets = {
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css": "static/docs/swagger-ui.css",
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js": "static/docs/swagger-ui-bundle.js",
    "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js": "static/docs/redoc.standalone.js",
    "https://fastapi.tiangolo.com/img/favicon.png": "static/docs/favicon.png"
}

# Create static/docs directory if it doesn't exist
os.makedirs("static/docs", exist_ok=True)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

for url, filepath in assets.items():
    print(f"Downloading {url} to {filepath}...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            with open(filepath, 'wb') as out_file:
                out_file.write(response.read())
        print("Success!")
    except Exception as e:
        print(f"Failed to download {url}: {e}")
