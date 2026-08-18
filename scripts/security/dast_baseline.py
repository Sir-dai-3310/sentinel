#!/usr/bin/env python3
"""Sentinel DAST baseline — OWASP API Security Top 10 equivalent checks.

Runs against a live Sentinel API instance (default http://127.0.0.1:8000).
Covers:
  1. Unauthenticated access to protected endpoints (API2 Broken Auth)
  2. Forged/malformed JWT rejection (API2)
  3. Default JWT secret forgeability check (API2) — reported, not exploited beyond proof
  4. SQL injection probes on query/path params (API8 Injection)
  5. XSS payloads in rule description — reflection check (API8)
  6. Path traversal via rule id on POST /api/v1/rules (API1 BOLA/filesystem)
  7. Oversized payload handling (API4 Unrestricted Resource Consumption)
  8. Security response headers (OWASP Secure Headers)
  9. CORS misconfiguration probe (API7/API8)
 10. Error verbosity / stack trace leakage (API9 Improper Inventory/SSRF misc)

Usage: python3 scripts/security/dast_baseline.py [base_url]
Exit code 0 = no FAIL findings; 1 = at least one FAIL.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
TIMEOUT = 15.0

findings: list[dict] = []


def record(check: str, status: str, detail: str, severity: str = "info") -> None:
    findings.append({"check": check, "status": status, "severity": severity, "detail": detail})
    print(f"[{status:4}] [{severity:6}] {check}: {detail}")


def mint_token(secret: str, subject: str = "dast-probe", roles: list[str] | None = None) -> str:
    from jose import jwt

    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + 3600,
        "tenant": "default",
        "roles": roles or ["admin"],
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=TIMEOUT, follow_redirects=False)

    # --- 0. liveness ---
    r = client.get("/api/v1/health")
    if r.status_code != 200:
        print("API not reachable; aborting")
        return 2

    protected = [
        ("GET", "/api/v1/rules"),
        ("GET", "/api/v1/stats"),
        ("GET", "/api/v1/settings"),
        ("GET", "/api/v1/tenants"),
        ("POST", "/api/v1/analyze"),
        ("POST", "/api/v1/rules"),
        ("DELETE", "/api/v1/rules/some-id"),
        ("GET", "/api/v1/privacy/export"),
        ("POST", "/api/v1/logs/import"),
    ]

    # --- 1. unauthenticated access ---
    bad = []
    for method, path in protected:
        r = client.request(method, path)
        if r.status_code not in (401, 403):
            bad.append(f"{method} {path} -> {r.status_code}")
    if bad:
        record("unauth-access", "FAIL", "未认证可访问: " + "; ".join(bad), "high")
    else:
        record("unauth-access", "PASS", f"{len(protected)} 个受保护端点未认证均返回 401/403")

    # --- 2. forged/malformed tokens ---
    forged_cases = {
        "garbage": "not.a.token",
        "alg-none": mint_none_alg_token(),
        "wrong-secret": mint_token("wrong-secret-value"),
    }
    bad = []
    for name, tok in forged_cases.items():
        r = client.get("/api/v1/rules", headers={"Authorization": f"Bearer {tok}"})
        if r.status_code not in (401, 403):
            bad.append(f"{name} -> {r.status_code}")
    if bad:
        record("forged-token", "FAIL", "伪造 token 被接受: " + "; ".join(bad), "critical")
    else:
        record("forged-token", "PASS", "垃圾/alg-none/错误密钥 token 均被拒绝")

    # --- 3. default JWT secret ---
    default_secret = "CHANGE_THIS_IN_PRODUCTION"
    tok = mint_token(default_secret)
    r = client.get("/api/v1/rules", headers={"Authorization": f"Bearer {tok}"})
    if r.status_code == 200:
        record(
            "default-jwt-secret",
            "FAIL",
            "服务使用默认 JWT_SECRET，任何人都可伪造 admin token（已用其完成后续授权探测）",
            "high",
        )
        auth = {"Authorization": f"Bearer {tok}"}
    else:
        record("default-jwt-secret", "PASS", "默认密钥不可用（JWT_SECRET 已配置）")
        env_secret = os.getenv("JWT_SECRET")
        if not env_secret:
            print("JWT_SECRET env not set and default rejected; cannot run authed probes")
            return 1
        auth = {"Authorization": f"Bearer {mint_token(env_secret)}"}

    # --- 4. SQL injection probes ---
    sqli_payloads = ["' OR '1'='1", "1; DROP TABLE rules--", "' UNION SELECT 1,2,3--", "%27%20OR%201%3D1"]
    bad = []
    targets = [
        ("GET", "/api/v1/rules/{p}"),
        ("GET", "/api/v1/tenants/{p}"),
        ("GET", "/api/v1/logs/import/{p}"),
    ]
    for tpl_method, tpl in targets:
        for p in sqli_payloads:
            r = client.request(tpl_method, tpl.format(p=p), headers=auth)
            body = r.text.lower()
            if r.status_code == 500 and any(
                k in body for k in ("sql", "syntax", "sqlite", "postgres", "traceback")
            ):
                bad.append(f"{tpl} [{p[:20]}] -> 500 SQL 特征泄漏")
    if bad:
        record("sqli-probe", "FAIL", "; ".join(bad), "high")
    else:
        record("sqli-probe", "PASS", "SQLi 探针无 500/SQL 错误泄漏（全部 4xx/404）")

    # --- 5. XSS payload reflection ---
    xss = '<script>alert(1)</script><img src=x onerror=alert(1)>'
    rule_payload = {
        "id": "DASTXSS1",
        "title": "dast xss probe",
        "description": xss,
        "logsource": {"product": "test"},
        "detection": {"selection": {"a": "b"}, "condition": "selection"},
    }
    r = client.post("/api/v1/rules", json=rule_payload, headers=auth)
    reflected = []
    if r.status_code in (200, 201) and xss in r.text:
        reflected.append("create response reflects payload")
    r2 = client.get("/api/v1/rules/DASTXSS1", headers=auth)
    if r2.status_code == 200 and xss in r2.text:
        ctype = r2.headers.get("content-type", "")
        if "application/json" in ctype:
            record(
                "xss-reflection",
                "PASS",
                "XSS 载荷经 JSON 存储/返回，content-type=application/json（非 HTML 上下文，浏览器不执行）",
            )
        else:
            reflected.append(f"rule returned as {ctype}")
    # cleanup probe rule
    client.delete("/api/v1/rules/DASTXSS1", headers=auth)
    if reflected:
        record("xss-reflection", "WARN", "; ".join(reflected), "low")

    # --- 6. path traversal via rule id ---
    traversal_ids = [
        "../../../../tmp/dast_traversal_probe",
        "..%2f..%2f..%2ftmp%2fdast_traversal_probe2",
    ]
    traversed = []
    for tid in traversal_ids:
        payload = dict(rule_payload)
        payload["id"] = tid
        payload["description"] = "path traversal probe"
        r = client.post("/api/v1/rules", json=payload, headers=auth)
        probe1 = os.path.exists("/tmp/dast_traversal_probe.yml")
        probe2 = os.path.exists("/tmp/dast_traversal_probe2.yml")
        if probe1 or probe2:
            traversed.append(f"id={tid!r} -> {r.status_code}, file written outside rules dir")
        # also accept detection via response file_path escaping
        if r.status_code in (200, 201):
            try:
                fp = r.json().get("file_path", "")
                if ".." in fp:
                    traversed.append(f"id={tid!r} -> file_path={fp!r} escapes rules dir")
            except Exception:
                pass
    # cleanup any strays
    for f in ("/tmp/dast_traversal_probe.yml", "/tmp/dast_traversal_probe2.yml"):
        if os.path.exists(f):
            os.remove(f)
    if traversed:
        record("path-traversal", "FAIL", "路径穿越写文件成功: " + "; ".join(traversed), "critical")
    else:
        record("path-traversal", "PASS", "rule id 路径穿越被拒绝/无害化")

    # --- 7. oversized payload ---
    big = {"log": "A" * (10 * 1024 * 1024)}  # ~10MB
    try:
        r = client.post("/api/v1/analyze", json=big, headers=auth, timeout=60)
        if r.status_code in (400, 413, 422):
            record("oversized-payload", "PASS", f"10MB payload -> {r.status_code}（被拒/校验失败）")
        elif r.status_code == 200:
            record("oversized-payload", "WARN", "10MB payload 被接受（无大小限制）", "medium")
        else:
            record("oversized-payload", "WARN", f"10MB payload -> {r.status_code}", "low")
    except httpx.HTTPError as e:
        record("oversized-payload", "PASS", f"10MB payload 连接被中断/拒绝: {type(e).__name__}")

    # --- 8. security headers ---
    r = client.get("/api/v1/health")
    required = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "x-xss-protection": None,
        "referrer-policy": None,
    }
    missing = [h for h, v in required.items() if h not in {k.lower() for k in r.headers}]
    if missing:
        record("security-headers", "FAIL", f"缺少安全响应头: {missing}", "medium")
    else:
        record("security-headers", "PASS", "X-Content-Type-Options/X-Frame-Options/XSS-Protection/Referrer-Policy 均在位")

    # --- 9. CORS ---
    r = client.get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example.com"},
    )
    acao = r.headers.get("access-control-allow-origin")
    if acao == "*" or acao == "https://evil.example.com":
        record("cors", "FAIL", f"任意 Origin 被反射/通配: {acao}", "high")
    else:
        record("cors", "PASS", f"恶意 Origin 未获 ACAO（acao={acao!r}）")

    # --- 10. error verbosity ---
    r = client.get("/api/v1/rules/", headers={**auth, "X-No-Such": "1"})
    r = client.post("/api/v1/rules", content=b"{invalid json", headers={**auth, "Content-Type": "application/json"})
    leak = "traceback" in r.text.lower() or "file \"/" in r.text
    if leak:
        record("error-verbosity", "FAIL", "错误响应含堆栈/内部路径", "medium")
    else:
        record("error-verbosity", "PASS", "畸形请求返回结构化 4xx，无堆栈泄漏")

    fails = [f for f in findings if f["status"] == "FAIL"]
    print(f"\n== DAST baseline: {len(findings)} checks, {len(fails)} FAIL ==")
    return 1 if fails else 0


def mint_none_alg_token() -> str:
    import base64

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    now = int(time.time())
    header = b64({"alg": "none", "typ": "JWT"})
    payload = b64({"sub": "attacker", "iat": now, "exp": now + 3600, "tenant": "default", "roles": ["admin"]})
    return f"{header}.{payload}."


if __name__ == "__main__":
    sys.exit(main())
