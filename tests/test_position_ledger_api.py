from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stock_ai.api import routes
from stock_ai.db.session import get_db
from stock_ai.main import SafeJSONResponse


@pytest.fixture
def client(db_session):
    app = FastAPI(default_response_class=SafeJSONResponse)
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client


def buy(client, quantity, price, date):
    response = client.post("/positions/IREN/buy", json={"quantity": quantity, "price_per_share": price, "transaction_date": date})
    assert response.status_code == 200, response.text
    return response.json()


def test_dated_preview_and_confirmation_have_same_wire_values(client):
    buy(client, "10", "10", "2026-09-18T00:00:00Z")
    buy(client, "10", "20", "2026-09-20T00:00:00Z")
    inputs = {"quantity": "5", "price_per_share": "30", "fees": "0", "transaction_date": "2026-09-19T00:00:00Z"}
    response = client.get("/positions/IREN/sell-preview", params=inputs)
    assert response.status_code == 200
    preview = response.json()
    assert Decimal(str(preview["cost_basis_total"])) == Decimal("50")
    assert client.post("/positions/IREN/sell", json=inputs).status_code == 200
    sale = client.get("/positions/transactions", params={"transaction_type": "SELL"}).json()[0]
    for field in ("cost_basis_total", "sale_proceeds", "realized_profit_loss", "realized_profit_loss_pct"):
        assert Decimal(str(preview[field])) == Decimal(str(sale[field]))
    assert len(client.get("/positions/transactions").json()) == 3


def test_oversell_returns_400_without_orphan_transaction(client):
    buy(client, "10", "10", "2026-09-18T00:00:00Z")
    response = client.post("/positions/IREN/sell", json={"quantity": "11", "price_per_share": "20"})
    assert response.status_code == 400
    assert "currently own 10" in response.json()["detail"]
    assert len(client.get("/positions/transactions").json()) == 1


def test_patch_accepts_annotations_and_rejects_accounting_fields(client):
    position = buy(client, "10", "10", "2026-09-18T00:00:00Z")
    response = client.patch(f"/positions/{position['id']}", json={"notes": "updated", "my_target_price": 20})
    assert response.status_code == 200
    for field, value in (("shares", 1), ("purchase_price", 5), ("purchase_date", "2026-09-17")):
        assert client.patch(f"/positions/{position['id']}", json={field: value}).status_code == 422
    assert client.get("/positions").json()[0]["notes"] == "updated"


def test_close_rebuy_delete_and_summary_agree(client, monkeypatch):
    inputs = {"quantity": "3", "price_per_share": "10", "fees": "0.01", "transaction_date": "2026-09-18T00:00:00Z"}
    assert client.post("/positions/IREN/buy", json=inputs).status_code == 200
    for day in (19, 20, 21):
        assert client.post("/positions/IREN/sell", json={"quantity": "1", "price_per_share": "10", "transaction_date": f"2026-09-{day}T00:00:00Z"}).status_code == 200
    assert client.get("/positions").json() == []
    closed = client.get("/positions/closed").json()[0]
    assert Decimal(str(closed["realized_profit_loss"])) == Decimal("-0.01")
    position = buy(client, "1", "20", "2026-09-22T00:00:00Z")
    assert position["cycle_index"] == 2
    assert Decimal(str(position["realized_pl"])) == 0
    assert client.get("/positions/closed").json()[0] == closed
    monkeypatch.setattr(routes, "get_market_data_provider", lambda: None)
    monkeypatch.setattr(routes, "get_quotes", lambda *args: {"IREN": SimpleNamespace(price=Decimal("21"))})
    summary = client.get("/positions/summary").json()
    assert Decimal(str(summary["realized_pl"])) == Decimal("-0.01")
    assert Decimal(str(summary["unrealized_pl"])) == Decimal("1")
    assert Decimal(str(summary["total_pl"])) == Decimal("0.99")
    sale = next(t for t in client.get("/positions/transactions").json() if t["transaction_type"] == "SELL")
    assert client.delete(f"/positions/transactions/{sale['id']}").status_code == 200
    assert client.get("/positions/closed").json() == []
    assert client.get("/positions").json()[0]["cycle_index"] == 1


def test_api_rejects_subprecision_trade(client):
    assert client.post("/positions/IREN/buy", json={"quantity": "0.0000001", "price_per_share": "10"}).status_code == 422
    assert client.get("/positions/transactions").json() == []
    assert client.get("/positions/IREN/sell-preview", params={"quantity": "0.0000001", "price_per_share": "10"}).status_code == 422


def test_api_history_offset_is_forwarded(client):
    buy(client, "1", "10", "2026-09-18T00:00:00Z")
    buy(client, "1", "20", "2026-09-19T00:00:00Z")
    first = client.get("/positions/transactions", params={"limit": 1, "offset": 0}).json()
    second = client.get("/positions/transactions", params={"limit": 1, "offset": 1}).json()
    assert first[0]["id"] != second[0]["id"]
    assert second[0]["price_per_share"] == "10.000000"
