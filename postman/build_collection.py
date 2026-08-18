"""Generate postman/sentinel.postman_collection.json from the live OpenAPI schema.

Run from the repo root:

    python3 postman/build_collection.py [openapi_url] [out_path]

Defaults to http://127.0.0.1:8000/openapi.json. Regenerate whenever endpoints change.
"""

import json
import sys
import urllib.request

DEFAULT_OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"
DEFAULT_OUT = "postman/sentinel.postman_collection.json"

FOLDER_ORDER = [
    "auth", "health", "analysis", "logs", "rules", "stats", "settings",
    "tenants", "privacy",
]

LOGIN_TEST_SCRIPT = [
    "const body = pm.response.json();",
    "if (body.access_token) {",
    '    pm.collectionVariables.set("token", body.access_token);',
    '    console.log("token saved to collection variable");',
    "}",
]


def request_item(name, method, path, spec, base_var="{{base_url}}"):
    segments = [p for p in path.split("/") if p]
    item = {
        "name": name,
        "request": {
            "method": method.upper(),
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": {
                "raw": f"{base_var}{path}",
                "host": [base_var],
                "path": segments,
            },
        },
    }
    req = item["request"]
    body = spec.get("requestBody", {})
    content = body.get("content", {})
    if method.upper() in ("POST", "PUT"):
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            req["body"] = {
                "mode": "raw",
                "raw": json.dumps(example_for(schema), indent=2),
            }
        elif "multipart/form-data" in content:
            schema = content["multipart/form-data"].get("schema", {})
            props = schema.get("properties", {})
            formdata = []
            for key, prop in props.items():
                # FastAPI >=0.140 emits contentMediaType; older uses format: binary
                if prop.get("format") == "binary" or prop.get("contentMediaType"):
                    formdata.append({"key": key, "type": "file", "src": ""})
                else:
                    formdata.append({"key": key, "type": "text", "value": ""})
            req["body"] = {"mode": "formdata", "formdata": formdata}
            req["header"] = [h for h in req["header"] if h["key"] != "Content-Type"]
    query = []
    for param in spec.get("parameters", []):
        if param.get("in") == "query":
            query.append({
                "key": param["name"],
                "value": "",
                "description": (param.get("description") or param.get("schema", {}).get("description") or ""),
            })
    if query:
        req["url"]["query"] = query
    if path.endswith("/auth/login") and method.lower() == "post":
        item["event"] = [{
            "listen": "test",
            "script": {"type": "text/javascript", "exec": LOGIN_TEST_SCRIPT},
        }]
    return item


def example_for(schema, _depth=0):
    """Fabricate a plausible example payload from a JSON schema."""
    if _depth > 4:
        return {}
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        schema = {"$ref": schema["$ref"]}  # resolved by caller via REFS
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        return {
            k: example_for(v, _depth + 1)
            for k, v in schema.get("properties", {}).items()
        }
    if t == "array":
        return [example_for(schema.get("items", {}), _depth + 1)]
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return True
    fmt = schema.get("format")
    if fmt == "date-time":
        return "2026-01-01T00:00:00Z"
    return schema.get("default", "string")


def resolve_refs(node, components):
    """Inline $ref one level deep for nicer examples."""
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/components/schemas/"):
            name = node["$ref"].rsplit("/", 1)[-1]
            target = components.get("schemas", {}).get(name)
            if target is not None:
                merged = dict(target)
                for k, v in node.items():
                    if k != "$ref":
                        merged[k] = v
                return resolve_refs(merged, components)
        return {k: resolve_refs(v, components) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_refs(v, components) for v in node]
    return node


def build(openapi):
    components = openapi.get("components", {})
    paths = resolve_refs(openapi["paths"], components)

    folders = {tag: [] for tag in FOLDER_ORDER}
    uncategorized = []
    for path, methods in sorted(paths.items()):
        for method, spec in sorted(methods.items()):
            tag = (spec.get("tags") or ["uncategorized"])[0]
            summary = spec.get("summary") or spec.get("operationId") or f"{method.upper()} {path}"
            item = request_item(summary, method, path, spec)
            # read auth from OpenAPI security (we add a bearer variable per collection)
            if tag in folders:
                folders[tag].append(item)
            else:
                uncategorized.append(item)

    collection = {
        "info": {
            "_postman_id": "sentinel-api-v12",
            "name": "Sentinel API v1.2",
            "description": (
                "Complete collection for the Sentinel API. Set {{base_url}} "
                "(e.g. http://127.0.0.1:8000) and run 'Login' first — its test "
                "script stores the JWT into the {{token}} collection variable "
                "used by the collection-level Bearer auth."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}],
        },
        "variable": [
            {"key": "base_url", "value": "http://127.0.0.1:8000"},
            {"key": "token", "value": ""},
        ],
        "item": [],
    }
    for tag in FOLDER_ORDER:
        if folders[tag]:
            collection["item"].append({"name": tag, "item": folders[tag]})
    if uncategorized:
        collection["item"].append({"name": "uncategorized", "item": uncategorized})
    return collection


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OPENAPI_URL
    out = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT
    with urllib.request.urlopen(url, timeout=10) as r:
        openapi = json.load(r)
    collection = build(openapi)
    with open(out, "w") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)
    n = sum(len(f["item"]) for f in collection["item"])
    print(f"wrote {out}: {n} requests across {len(collection['item'])} folders")


if __name__ == "__main__":
    main()
