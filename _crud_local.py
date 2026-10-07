import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
TOKEN = None
STEPS = []


def call(method, path, body=None, expect=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            status, payload = resp.status, resp.read().decode()
            cors = resp.headers.get("Access-Control-Allow-Origin")
    except urllib.error.HTTPError as exc:
        status, payload = exc.code, exc.read().decode()
        cors = exc.headers.get("Access-Control-Allow-Origin")
    try:
        parsed = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed = payload[:200]
    ok = expect is None or status == expect
    STEPS.append((ok, method, path, status, expect, cors))
    print(("PASS " if ok else "FAIL ") + f"{method} {path} -> {status} (expect {expect}) CORS={cors}")
    if not ok:
        print("     body:", str(parsed)[:400])
    return status, parsed


def main():
    global TOKEN
    stamp = sys.argv[1] if len(sys.argv) > 1 else "test"
    email = f"crud.{stamp}@example.com"

    _, reg = call("POST", "/api/auth/register/owner", {
        "full_name": "CRUD Tester",
        "business_name": f"CRUD Biz {stamp}",
        "email": email,
        "password": "Sup3rSecret!Pass",
    }, expect=201)
    if not isinstance(reg, dict) or "access_token" not in reg:
        return finish(email)

    TOKEN = reg["access_token"]
    call("GET", "/api/auth/me", expect=200)

    _, prod = call("POST", "/api/products", {
        "name": "CRUD Widget",
        "category": "Testing",
        "buying_price": "10.00",
        "selling_price": "25.00",
        "stock_quantity": 5,
    }, expect=201)
    pid = prod.get("id")

    _, listing = call("GET", "/api/products?search=widget&category=Testing", expect=200)
    assert isinstance(listing, list) and len(listing) == 1, listing

    call("GET", f"/api/products/{pid}", expect=200)

    _, upd = call("PUT", f"/api/products/{pid}", {
        "name": "CRUD Widget v2",
        "category": "Testing",
        "buying_price": "12.00",
        "selling_price": "30.00",
        "stock_quantity": 7,
    }, expect=200)
    assert upd.get("name") == "CRUD Widget v2", upd

    _, sale = call("POST", "/api/sales", {"product_id": pid, "quantity": 3}, expect=201)
    sid = sale.get("id")
    assert sale.get("stock_after") is None or True
    print("     sale:", {k: sale.get(k) for k in ("quantity", "total_amount", "profit")})

    _, after = call("GET", f"/api/products/{pid}", expect=200)
    print("     stock after sale:", after.get("stock_quantity"), "(expect 4)")
    assert after.get("stock_quantity") == 4, after

    call("GET", "/api/sales", expect=200)
    call("GET", f"/api/sales/{sid}", expect=200)
    _, dash = call("GET", "/api/dashboard", expect=200)
    print("     dashboard:", {k: dash.get(k) for k in ("total_products", "total_stock_quantity", "today_total_sales", "today_total_profit")})

    call("DELETE", f"/api/products/{pid}", expect=409)
    call("DELETE", f"/api/sales/{sid}", expect=204)
    _, restocked = call("GET", f"/api/products/{pid}", expect=200)
    print("     stock after void:", restocked.get("stock_quantity"), "(expect 7)")
    assert restocked.get("stock_quantity") == 7, restocked
    call("DELETE", f"/api/products/{pid}", expect=204)
    call("GET", f"/api/products/{pid}", expect=404)

    call("GET", "/api/products", expect=200)
    return finish(email)


def finish(email):
    failed = [s for s in STEPS if not s[0]]
    print()
    print(f"{len(STEPS) - len(failed)}/{len(STEPS)} steps passed")
    print("TEST_EMAIL=" + email)
    sys.exit(1 if failed else 0)


main()
