"""组件 3、4 的组件测试，对应测试报告中各 10 条记录。

在 green-commute 目录运行：
    python -m pytest -q tests/test_component_34.py

tests/conftest.py 会将数据库指向临时 SQLite 文件。每条用例重新建立
演示数据，以免测试之间相互影响。
"""

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
    with TestClient(app) as test_client:
        yield test_client


def login(client, username="resident", password="Demo@123456"):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def request(client, method, path, headers, body=None):
    call = getattr(client, method)
    if body is None:
        return call(path, headers=headers)
    return call(path, headers=headers, json=body)


def award_bus_points(client, resident, distance="30", trip_id="component-34-trip"):
    response = request(
        client, "post", "/api/trips", resident,
        {"client_trip_id": trip_id, "mode": "bus", "distance_km": distance},
    )
    assert response.status_code == 200, response.text
    return response


def product_one(client, resident):
    products = request(client, "get", "/api/products", resident).json()
    return next(item for item in products if item["id"] == 1)


def redeem_product_one(client, resident):
    response = request(client, "post", "/api/redemptions", resident, {"product_id": 1})
    assert response.status_code == 200, response.text
    return response.json()["redemption"]


# 组件 3：积分账本与兑换退款，记录 1～10。
def test_component3_01_insufficient_points(client):
    resident = login(client)
    before_stock = product_one(client, resident)["stock"]
    response = request(client, "post", "/api/redemptions", resident, {"product_id": 1})
    assert response.status_code == 409
    assert "积分" in response.json()["detail"]
    assert request(client, "get", "/api/redemptions", resident).json() == []
    assert request(client, "get", "/api/wallet", resident).json()["balance"] == 0
    assert product_one(client, resident)["stock"] == before_stock


def test_component3_02_redeem_deducts_points_and_stock(client):
    resident = login(client)
    award_bus_points(client, resident)
    before_stock = product_one(client, resident)["stock"]
    order = redeem_product_one(client, resident)
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert order["status"] == "TO_FULFILL"
    assert wallet["balance"] == 21
    assert sorted(item["delta"] for item in wallet["transactions"]) == [-12, 33]
    assert product_one(client, resident)["stock"] == before_stock - 1


def test_component3_03_sold_out_does_not_charge(client):
    resident = login(client)
    award_bus_points(client, resident, distance="100")
    with SessionLocal() as db:
        product = db.get(Product, 1)
        product.stock = 0
        db.commit()
    before = request(client, "get", "/api/wallet", resident).json()
    response = request(client, "post", "/api/redemptions", resident, {"product_id": 1})
    after = request(client, "get", "/api/wallet", resident).json()
    assert response.status_code == 409
    assert after["balance"] == before["balance"]
    assert after["transaction_count"] == before["transaction_count"]
    assert request(client, "get", "/api/redemptions", resident).json() == []


def test_component3_04_refund_restores_points_and_stock(client):
    resident = login(client)
    award_bus_points(client, resident)
    before_stock = product_one(client, resident)["stock"]
    order = redeem_product_one(client, resident)
    response = request(
        client, "post", f"/api/redemptions/{order['id']}/refund", resident
    )
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert response.status_code == 200
    assert response.json()["redemption"]["status"] == "REFUNDED"
    assert wallet["balance"] == 33
    assert wallet["transactions"][0]["kind"] == "REFUND"
    assert wallet["transactions"][0]["delta"] == 12
    assert product_one(client, resident)["stock"] == before_stock


def test_component3_05_fulfilled_order_cannot_be_refunded(client):
    resident, merchant = login(client), login(client, "merchant")
    award_bus_points(client, resident)
    order = redeem_product_one(client, resident)
    fulfilled = request(
        client, "post", f"/api/merchant/orders/{order['id']}/fulfill", merchant
    )
    refund = request(
        client, "post", f"/api/redemptions/{order['id']}/refund", resident
    )
    assert fulfilled.status_code == 200
    assert refund.status_code == 409
    assert request(client, "get", "/api/wallet", resident).json()["balance"] == 21
    assert product_one(client, resident)["stock"] == 39


def test_component3_06_repeated_refund_is_idempotent(client):
    resident = login(client)
    award_bus_points(client, resident)
    order = redeem_product_one(client, resident)
    path = f"/api/redemptions/{order['id']}/refund"
    first = request(client, "post", path, resident)
    second = request(client, "post", path, resident)
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert first.status_code == second.status_code == 200
    assert second.json()["redemption"]["status"] == "REFUNDED"
    assert wallet["balance"] == 33
    assert wallet["transaction_count"] == 3
    assert product_one(client, resident)["stock"] == 40


def test_component3_07_trip_business_id_prevents_duplicate_award(client):
    resident = login(client)
    first = award_bus_points(client, resident, distance="10", trip_id="same-trip")
    same = award_bus_points(client, resident, distance="10", trip_id="same-trip")
    changed = request(
        client, "post", "/api/trips", resident,
        {"client_trip_id": "same-trip", "mode": "bus", "distance_km": "12"},
    )
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert first.json()["balance"] == same.json()["balance"] == 11
    assert changed.status_code == 409
    assert len(request(client, "get", "/api/trips", resident).json()) == 1
    assert wallet["balance"] == 11 and wallet["transaction_count"] == 1


def test_component3_08_zero_point_trip_has_no_ledger_entry(client):
    resident = login(client)
    response = request(
        client, "post", "/api/trips", resident,
        {"client_trip_id": "zero-point-walk", "mode": "walk", "distance_km": "0.01"},
    )
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert response.status_code == 200
    assert response.json()["trip"]["points"] == 0
    assert len(request(client, "get", "/api/trips", resident).json()) == 1
    assert wallet["balance"] == 0
    assert wallet["transactions"] == []


def test_component3_09_wallet_summary_matches_ledger(client):
    resident = login(client)
    award_bus_points(client, resident)
    order = redeem_product_one(client, resident)
    response = request(
        client, "post", f"/api/redemptions/{order['id']}/refund", resident
    )
    assert response.status_code == 200
    wallet = request(client, "get", "/api/wallet", resident).json()
    assert wallet["balance"] == 33
    assert wallet["transaction_count"] == 3
    assert sorted(item["delta"] for item in wallet["transactions"]) == [-12, 12, 33]
    assert sum(item["delta"] for item in wallet["transactions"]) == wallet["balance"]
    assert wallet["consistent"] is True


def test_component3_10_wallet_cursor_pagination(client):
    resident = login(client)
    award_bus_points(client, resident)
    redeem_product_one(client, resident)
    first_page = client.get("/api/wallet", headers=resident, params={"limit": 1})
    assert first_page.status_code == 200
    assert [row["delta"] for row in first_page.json()["transactions"]] == [-12]
    cursor = first_page.json()["next_before_id"]
    assert cursor is not None
    second_page = client.get(
        "/api/wallet", headers=resident, params={"limit": 1, "before_id": cursor}
    )
    assert second_page.status_code == 200
    assert [row["delta"] for row in second_page.json()["transactions"]] == [33]
    assert second_page.json()["next_before_id"] is None


# 组件 4：商户经营与库存履约，记录 1～10。
def test_component4_01_merchant_publishes_product(client):
    merchant, resident = login(client, "merchant"), login(client)
    response = request(
        client, "post", "/api/merchant/products", merchant,
        {"name": "环保补贴券", "description": "组件测试商品", "category": "交通优惠",
         "icon": "gift", "cost": 3, "stock": 2},
    )
    assert response.status_code == 201
    assert response.json()["stock"] == 2
    assert any(
        item["name"] == "环保补贴券"
        for item in request(client, "get", "/api/products", resident).json()
    )


def test_component4_02_blank_product_name_is_rejected(client):
    merchant = login(client, "merchant")
    before = len(request(client, "get", "/api/merchant/products", merchant).json())
    response = request(
        client, "post", "/api/merchant/products", merchant,
        {"name": "  ", "description": "空白名称", "category": "生活好物",
         "icon": "gift", "cost": 5, "stock": 1},
    )
    assert response.status_code == 422
    assert len(request(client, "get", "/api/merchant/products", merchant).json()) == before


def test_component4_03_zero_inventory_adjustment_is_rejected(client):
    merchant = login(client, "merchant")
    before = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    response = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "zero-adjustment", "quantity": 0, "note": "无效变更"},
    )
    after = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert response.status_code == 422
    assert after["product"]["stock"] == before["product"]["stock"]
    assert len(after["movements"]) == len(before["movements"])


def test_component4_04_inventory_cannot_be_overdrawn(client):
    merchant = login(client, "merchant")
    response = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "overdraw-41", "quantity": -41, "note": "超过库存"},
    )
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert response.status_code == 409
    assert history["product"]["stock"] == 40
    assert not any(row["operation_id"] == "overdraw-41" for row in history["movements"])


def test_component4_05_repeated_restock_adds_stock_once(client):
    merchant = login(client, "merchant")
    body = {"operation_id": "restock-once", "quantity": 5, "note": "补货五件"}
    first = request(client, "post", "/api/merchant/products/1/inventory", merchant, body)
    second = request(client, "post", "/api/merchant/products/1/inventory", merchant, body)
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant).json()
    assert first.status_code == second.status_code == 200
    assert first.json()["product"]["stock"] == second.json()["product"]["stock"] == 45
    assert sum(row["operation_id"] == "restock-once" for row in history["movements"]) == 1


def test_component4_06_unlisted_product_is_hidden_from_residents(client):
    merchant, resident = login(client, "merchant"), login(client)
    response = request(client, "patch", "/api/merchant/products/1", merchant, {"active": False})
    merchant_products = request(client, "get", "/api/merchant/products", merchant).json()
    resident_products = request(client, "get", "/api/products", resident).json()
    assert response.status_code == 200 and response.json()["active"] is False
    assert any(item["id"] == 1 and item["active"] is False for item in merchant_products)
    assert all(item["id"] != 1 for item in resident_products)


def test_component4_07_merchant_cannot_read_other_store_inventory(client):
    admin = login(client, "admin")
    created = request(
        client, "post", "/api/admin/merchants", admin,
        {"username": "merchant_for_component4", "display_name": "第二家商户",
         "password": "merchant-pass-123"},
    )
    assert created.status_code == 201
    other_merchant = login(client, "merchant_for_component4", "merchant-pass-123")
    response = request(client, "get", "/api/merchant/products/1/inventory", other_merchant)
    assert response.status_code == 404


def test_component4_08_owner_merchant_fulfills_order(client):
    resident, merchant = login(client), login(client, "merchant")
    award_bus_points(client, resident)
    order = redeem_product_one(client, resident)
    response = request(
        client, "post", f"/api/merchant/orders/{order['id']}/fulfill", merchant
    )
    merchant_orders = request(client, "get", "/api/merchant/orders", merchant).json()
    assert response.status_code == 200
    assert response.json()["status"] == "FULFILLED"
    assert response.json()["fulfilled_at"] is not None
    assert len(merchant_orders) == 1
    assert merchant_orders[0]["redemption"]["status"] == "FULFILLED"


def test_component4_09_repeated_fulfillment_keeps_original_time(client):
    resident, merchant = login(client), login(client, "merchant")
    award_bus_points(client, resident)
    order = redeem_product_one(client, resident)
    path = f"/api/merchant/orders/{order['id']}/fulfill"
    first = request(client, "post", path, merchant)
    second = request(client, "post", path, merchant)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "FULFILLED"
    assert first.json()["fulfilled_at"] == second.json()["fulfilled_at"]
    assert len(request(client, "get", "/api/merchant/orders", merchant).json()) == 1


def test_component4_10_inventory_query_returns_current_stock_and_history(client):
    merchant = login(client, "merchant")
    adjustment = request(
        client, "post", "/api/merchant/products/1/inventory", merchant,
        {"operation_id": "history-restock-5", "quantity": 5, "note": "查询流水测试"},
    )
    history = request(client, "get", "/api/merchant/products/1/inventory", merchant)
    assert adjustment.status_code == history.status_code == 200
    assert history.json()["product"]["stock"] == 45
    assert any(
        row["operation_id"] == "history-restock-5"
        and row["kind"] == "ADJUSTMENT" and row["quantity"] == 5
        for row in history.json()["movements"]
    )
