"""图一第 4、5、6 项的功能测试。

执行方式：在 green-commute 目录运行
    pytest tests/test_functional_456.py -q

tests/conftest.py 会为本文件创建隔离的临时 SQLite 数据库。
每条测试对应报告中同一功能项的一条记录。
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Product


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SEED_DEMO_DATA", "1")
    monkeypatch.setenv("DEMO_PASSWORD", "Demo@123456")
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c


def login(c, username="resident"):
    response = c.post(
        "/api/auth/login",
        json={"username": username, "password": "Demo@123456"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def request(c, method, url, headers, body=None):
    if body is None:
        return getattr(c, method)(url, headers=headers)
    return getattr(c, method)(url, headers=headers, json=body)


def award_points(c, headers, trip_id="functional-456-trip", distance="30"):
    response = c.post(
        "/api/trips",
        headers=headers,
        json={"client_trip_id": trip_id, "mode": "bus", "distance_km": distance},
    )
    assert response.status_code == 200, response.text
    return response


def redeem_one(c, headers):
    response = request(c, "post", "/api/redemptions", headers, {"product_id": 1})
    assert response.status_code == 200, response.text
    return response.json()["redemption"]


# 4 积分商城、兑换与退款：报告记录 1～6。
def test_4_01_redeem_success(client):
    resident = login(client)
    award_points(client, resident)
    assert request(client, "get", "/api/wallet", resident).json()["balance"] == 33
    redemption = redeem_one(client, resident)
    assert redemption["status"] == "TO_FULFILL"
    assert request(client, "get", "/api/wallet", resident).json()["balance"] == 21
    product = next(p for p in request(client, "get", "/api/products", resident).json() if p["id"] == 1)
    assert product["stock"] == 39


def test_4_02_insufficient_points(client):
    resident = login(client)
    response = request(client, "post", "/api/redemptions", resident, {"product_id": 1})
    assert response.status_code == 409
    assert request(client, "get", "/api/redemptions", resident).json() == []
    product = next(p for p in request(client, "get", "/api/products", resident).json() if p["id"] == 1)
    assert product["stock"] == 40


def test_4_03_refund_before_fulfillment(client):
    resident = login(client)
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    response = request(client, "post", f"/api/redemptions/{redemption['id']}/refund", resident)
    assert response.status_code == 200
    assert response.json()["redemption"]["status"] == "REFUNDED"
    assert response.json()["balance"] == 33
    product = next(p for p in request(client, "get", "/api/products", resident).json() if p["id"] == 1)
    assert product["stock"] == 40
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert wallet["transactions"][0]["kind"] == "REFUND"
    assert wallet["transactions"][0]["delta"] == 12


def test_4_04_repeat_refund_does_not_return_points_twice(client):
    resident = login(client)
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    endpoint = f"/api/redemptions/{redemption['id']}/refund"
    assert request(client, "post", endpoint, resident).status_code == 200
    again = request(client, "post", endpoint, resident)
    assert again.status_code == 200
    assert again.json()["redemption"]["status"] == "REFUNDED"
    assert again.json()["balance"] == 33
    assert request(client, "get", "/api/wallet", resident).json()["transaction_count"] == 3
    product = next(p for p in request(client, "get", "/api/products", resident).json() if p["id"] == 1)
    assert product["stock"] == 40


def test_4_05_refund_after_fulfillment_is_rejected(client):
    resident, merchant = login(client), login(client, "merchant")
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    fulfilled = request(client, "post", f"/api/merchant/orders/{redemption['id']}/fulfill", merchant)
    assert fulfilled.status_code == 200
    refund = request(client, "post", f"/api/redemptions/{redemption['id']}/refund", resident)
    assert refund.status_code == 409
    orders = request(client, "get", "/api/redemptions", resident).json()
    assert orders[0]["status"] == "FULFILLED"


def test_4_06_only_one_concurrent_redemption_for_last_item(client):
    resident = login(client)
    award_points(client, resident, distance="100")
    with SessionLocal() as db:
        product = db.get(Product, 1)
        product.stock = 1
        db.commit()

    def submit(_):
        return request(client, "post", "/api/redemptions", resident, {"product_id": 1}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        status_codes = list(pool.map(submit, range(2)))
    assert sorted(status_codes) == [200, 409]
    assert len(request(client, "get", "/api/redemptions", resident).json()) == 1


# 5 商户商品、品类与库存管理：报告记录 1～6。
def test_5_01_publish_product(client):
    resident, merchant = login(client), login(client, "merchant")
    payload = {
        "name": "环保补贴券",
        "description": "功能测试商品",
        "category": "交通优惠",
        "icon": "gift",
        "cost": 3,
        "stock": 2,
    }
    created = request(client, "post", "/api/merchant/products", merchant, payload)
    assert created.status_code == 201
    assert created.json()["stock"] == 2
    assert any(p["name"] == "环保补贴券" for p in request(client, "get", "/api/products", resident).json())


def test_5_02_restock_and_inventory_history(client):
    merchant = login(client, "merchant")
    response = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "functional-restock-1", "quantity": 5, "note": "补充测试库存"},
    )
    assert response.status_code == 200
    assert response.json()["product"]["stock"] == 45
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert history["product"]["stock"] == 45
    assert any(m["kind"] == "ADJUSTMENT" and m["quantity"] == 5 for m in history["movements"])


def test_5_03_duplicate_inventory_operation_is_idempotent(client):
    merchant = login(client, "merchant")
    body = {"operation_id": "functional-restock-2", "quantity": 5, "note": "补充测试库存"}
    first = request(client, "post", "/api/merchant/products/1/inventory", merchant, body)
    second = request(client, "post", "/api/merchant/products/1/inventory", merchant, body)
    assert first.status_code == second.status_code == 200
    assert first.json()["product"]["stock"] == 45
    assert second.json()["product"]["stock"] == 45
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert sum(m["operation_id"] == body["operation_id"] for m in history["movements"]) == 1


def test_5_04_zero_and_overdraft_inventory_are_rejected(client):
    merchant = login(client, "merchant")
    zero = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "functional-zero", "quantity": 0, "note": "无效调整"},
    )
    overdraft = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "functional-overdraft", "quantity": -41, "note": "超过现有库存"},
    )
    assert zero.status_code == 422
    assert overdraft.status_code == 409
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert history["product"]["stock"] == 40


def test_5_05_blank_product_name_is_rejected(client):
    merchant = login(client, "merchant")
    before = len(request(client, "get", "/api/merchant/products", merchant).json())
    payload = {
        "name": "  ", "description": "名称为空白", "category": "生活好物",
        "icon": "gift", "cost": 5, "stock": 1,
    }
    response = request(client, "post", "/api/merchant/products", merchant, payload)
    assert response.status_code == 422
    assert len(request(client, "get", "/api/merchant/products", merchant).json()) == before


def test_5_06_product_down_and_up(client):
    resident, merchant = login(client), login(client, "merchant")
    down = request(client, "patch", "/api/merchant/products/1", merchant, {"active": False})
    assert down.status_code == 200 and down.json()["active"] is False
    assert all(p["id"] != 1 for p in request(client, "get", "/api/products", resident).json())
    up = request(client, "patch", "/api/merchant/products/1", merchant, {"active": True})
    assert up.status_code == 200 and up.json()["active"] is True
    assert any(p["id"] == 1 for p in request(client, "get", "/api/products", resident).json())


# 6 商户订单与核销：报告记录 1～4。
def test_6_01_merchant_can_see_own_order(client):
    resident, merchant = login(client), login(client, "merchant")
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    response = request(client, "get", "/api/merchant/orders", merchant)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["redemption"]["id"] == redemption["id"]
    assert response.json()[0]["settlement_status"] == "PENDING"


def test_6_02_merchant_can_fulfill_own_order(client):
    resident, merchant = login(client), login(client, "merchant")
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    response = request(client, "post", f"/api/merchant/orders/{redemption['id']}/fulfill", merchant)
    assert response.status_code == 200
    assert response.json()["status"] == "FULFILLED"
    assert response.json()["fulfilled_at"] is not None


def test_6_03_repeat_fulfillment_is_idempotent(client):
    resident, merchant = login(client), login(client, "merchant")
    award_points(client, resident)
    redemption = redeem_one(client, resident)
    endpoint = f"/api/merchant/orders/{redemption['id']}/fulfill"
    first = request(client, "post", endpoint, merchant)
    second = request(client, "post", endpoint, merchant)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "FULFILLED"
    assert first.json()["fulfilled_at"] == second.json()["fulfilled_at"]
    assert len(request(client, "get", "/api/merchant/orders", merchant).json()) == 1


def test_6_04_resident_cannot_view_merchant_orders(client):
    resident = login(client)
    response = request(client, "get", "/api/merchant/orders", resident)
    assert response.status_code == 403
