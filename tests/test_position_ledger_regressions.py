from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from stock_ai.db.session import get_engine, get_session_factory, init_db
from stock_ai.models.positions import Position, PositionTransaction
from stock_ai.schemas.positions import PositionBuy, PositionCreate, PositionSell, PositionUpdate
from stock_ai.services import positions as svc

D = Decimal
NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def buy(db, quantity, price="10", fees="0", day=0):
    return svc.buy_shares(db, "IREN", PositionBuy(quantity=D(quantity), price_per_share=D(price), fees=D(fees), transaction_date=NOW + timedelta(days=day)))


def sell(db, quantity, price="10", day=1):
    return svc.sell_shares(db, "IREN", PositionSell(quantity=D(quantity), price_per_share=D(price), transaction_date=NOW + timedelta(days=day)))


def test_real_upgrade_migrates_before_first_trade(test_settings):
    engine = get_engine(test_settings)
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE positions (
            id INTEGER PRIMARY KEY, ticker VARCHAR(16) NOT NULL,
            shares NUMERIC(18,6) NOT NULL, purchase_price NUMERIC(18,6) NOT NULL,
            purchase_date DATE NOT NULL, my_target_price NUMERIC(18,6),
            stop_loss_price NUMERIC(18,6), notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""))
        conn.execute(text("INSERT INTO positions (ticker,shares,purchase_price,purchase_date,notes) VALUES ('IREN',22,43.11,'2026-09-01','keep me')"))
    init_db(test_settings)
    init_db(test_settings)
    with get_session_factory(test_settings)() as db:
        position = svc.get_position_by_ticker(db, "IREN")
        assert (position.shares, position.purchase_price, position.total_cost_basis) == (D("22"), D("43.11"), D("948.42"))
        assert len(svc.list_transactions(db)) == 1
        position = buy(db, "1", "50")
        assert position.shares == D("23")
        assert position.total_cost_basis == D("998.42")
        assert position.notes == "keep me"
        sell(db, "1", "55")
        assert len(svc.list_transactions(db)) == 3


def test_service_buy_protects_unmigrated_holding(db_session):
    db_session.add(Position(ticker="IREN", shares=D("22"), purchase_price=D("43.11"), purchase_date=date(2026, 9, 1)))
    db_session.commit()
    assert buy(db_session, "1", "50").shares == D("23")
    assert len(svc.list_transactions(db_session)) == 2


def test_startup_migration_rolls_back_then_retries(db_session, test_settings, monkeypatch):
    db_session.add(Position(ticker="IREN", shares=D("22"), purchase_price=D("43.11"), purchase_date=date(2026, 9, 1)))
    db_session.commit()
    original = svc.rebuild_position
    def fail(*args):
        original(*args)
        args[0].flush()
        raise RuntimeError("upgrade interrupted")
    monkeypatch.setattr(svc, "rebuild_position", fail)
    with pytest.raises(RuntimeError):
        init_db(test_settings)
    with Session(db_session.get_bind()) as fresh:
        assert svc.list_transactions(fresh) == []
        assert svc.get_position_by_ticker(fresh, "IREN").shares == D("22")
    monkeypatch.setattr(svc, "rebuild_position", original)
    init_db(test_settings)
    with Session(db_session.get_bind()) as fresh:
        assert len(svc.list_transactions(fresh)) == 1
        assert svc.get_position_by_ticker(fresh, "IREN").total_cost_basis == D("948.42")


def test_split_sells_conserve_buy_fee_and_final_residual(db_session):
    buy(db_session, "3", fees="0.01")
    first = sell(db_session, "1")
    assert first.total_cost_basis == D("20.01")
    assert first.purchase_price == D("10.003333")
    sell(db_session, "1", day=2)
    sell(db_session, "1", day=3)
    closed = svc.closed_positions(db_session)[0]
    assert closed["total_cost_basis"] == D("30.01")
    assert closed["realized_profit_loss"] == D("-0.01")
    assert svc.realized_pl_total(db_session) == D("-0.01")


def test_fractional_purchase_capital_is_rounded_cumulatively(db_session):
    for day in range(3):
        buy(db_session, "1", "0.004", day=day)
    partial = sell(db_session, "2", "0.004", day=3)
    assert partial.total_cost_basis >= 0
    sell(db_session, "1", "0.004", day=4)
    assert svc.closed_positions(db_session)[0]["total_cost_basis"] == D("0.01")


def test_duplicate_legacy_rows_are_consolidated_before_unique_index(db_session, test_settings):
    db_session.execute(text("DROP INDEX ix_positions_ticker"))
    for quantity, price, notes in (("1", "10", "first"), ("2", "15", "second")):
        db_session.add(Position(ticker="IREN", shares=D(quantity), purchase_price=D(price), purchase_date=date(2026, 9, 1), notes=notes))
    db_session.commit()
    init_db(test_settings)
    with Session(db_session.get_bind()) as fresh:
        rows = list(fresh.scalars(select(Position)))
        assert len(rows) == 1
        assert rows[0].shares == D("3")
        assert rows[0].total_cost_basis == D("40")
        assert "first" in rows[0].notes and "second" in rows[0].notes
        assert len(svc.list_transactions(fresh)) == 2
    from sqlalchemy import inspect
    assert next(index for index in inspect(db_session.get_bind()).get_indexes("positions") if index["name"] == "ix_positions_ticker")["unique"]


def test_conservation_with_buy_after_partial_sell_and_rebuy(db_session):
    buy(db_session, "3", fees="0.01")
    sell(db_session, "1")
    buy(db_session, "2", "12", fees="0.02", day=2)
    sell(db_session, "1", "13", day=3)
    sell(db_session, "3", "13", day=4)
    first = svc.closed_positions(db_session)[0]
    assert first["total_cost_basis"] == D("54.03")
    assert first["realized_profit_loss"] == D("7.97")
    position = buy(db_session, "2", "20", day=5)
    assert (position.cycle_index, position.realized_pl, position.total_cost_basis) == (2, D("0"), D("40"))
    assert svc.closed_positions(db_session)[0] == first


def test_dated_preview_matches_replay_and_does_not_write(db_session):
    buy(db_session, "10", "10")
    buy(db_session, "10", "20", day=2)
    before = [(t.id, t.cycle_index, t.realized_profit_loss) for t in svc.list_transactions(db_session)]
    preview = svc.preview_sell(db_session, "IREN", D("5"), D("30"), transaction_date=NOW + timedelta(days=1))
    assert preview["cost_basis_total"] == D("50")
    assert [(t.id, t.cycle_index, t.realized_profit_loss) for t in svc.list_transactions(db_session)] == before
    sell(db_session, "5", "30")
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    for field in ("cost_basis_total", "sale_proceeds", "realized_profit_loss", "realized_profit_loss_pct"):
        assert preview[field] == getattr(entry, field)


def test_preview_uses_unrounded_average(db_session):
    buy(db_session, "300000", fees="1")
    preview = svc.preview_sell(db_session, "IREN", D("100000"), D("11"), transaction_date=NOW + timedelta(days=1))
    sell(db_session, "100000", "11")
    assert preview["cost_basis_total"] == D("1000000.33")
    assert svc.list_transactions(db_session, "IREN", "SELL")[0].cost_basis_total == preview["cost_basis_total"]


def test_preview_flags_invalid_historical_order(db_session):
    buy(db_session, "10", day=1)
    preview = svc.preview_sell(db_session, "IREN", D("5"), D("12"), transaction_date=NOW)
    assert preview["exceeds_position"]
    assert "held at that point" in preview["error"]
    assert len(svc.list_transactions(db_session)) == 1


def test_hidden_holding_stays_hidden_on_correction_and_resumes_on_buy(db_session):
    position = buy(db_session, "100", "30")
    position.notes = "annotation"
    db_session.commit()
    buy(db_session, "10", "40", day=1)
    extra = svc.list_transactions(db_session)[0]
    assert svc.delete_position(db_session, position.id)
    svc.delete_transaction(db_session, extra.id)
    assert svc.list_positions(db_session) == []
    assert svc.get_position(db_session, position.id).notes == "annotation"
    resumed = buy(db_session, "10", "40", day=2)
    assert resumed.id == position.id
    assert resumed.shares == D("110")
    assert resumed.notes == "annotation"
    assert resumed.cycle_index == 1  # hiding is not an economic sale


def test_first_buy_links_to_position(db_session):
    position = buy(db_session, "1")
    assert svc.list_transactions(db_session)[0].position_id == position.id


def test_delete_last_buy_does_not_migrate_zero_balance(db_session):
    position = buy(db_session, "1")
    svc.delete_transaction(db_session, svc.list_transactions(db_session)[0].id)
    assert svc.migrate_legacy_positions(db_session)["opening_transactions_created"] == 0
    assert svc.list_transactions(db_session) == []
    assert svc.get_position(db_session, position.id).shares == D("0")


def test_deleting_close_merges_and_replays_rebuy_cycle(db_session):
    buy(db_session, "10")
    sell(db_session, "10", "12")
    closing = svc.list_transactions(db_session, "IREN", "SELL")[0]
    buy(db_session, "10", "20", day=2)
    sell(db_session, "5", "25", day=3)
    position = svc.delete_transaction(db_session, closing.id)
    assert (position.shares, position.purchase_price, position.cycle_index) == (D("15"), D("15"), 1)
    assert position.realized_pl == D("50")
    assert svc.closed_positions(db_session) == []
    assert {t.cycle_index for t in svc.list_transactions(db_session)} == {1}


def test_invalid_deletion_rolls_back_every_sale_from_fresh_session(db_session):
    buy(db_session, "10")
    buy(db_session, "10", "20", day=2)
    sell(db_session, "5", "30")
    sell(db_session, "10", "30", day=3)
    before = [(t.id, t.cost_basis_total, t.realized_profit_loss, t.cycle_index) for t in svc.list_transactions(db_session)]
    extra = next(t for t in svc.list_transactions(db_session, "IREN", "BUY") if t.price_per_share == D("20"))
    with pytest.raises(svc.PositionError):
        svc.delete_transaction(db_session, extra.id)
    with Session(db_session.get_bind()) as fresh:
        assert [(t.id, t.cost_basis_total, t.realized_profit_loss, t.cycle_index) for t in svc.list_transactions(fresh)] == before
        assert svc.get_position_by_ticker(fresh, "IREN").shares == D("5")


def test_failed_first_buy_rolls_back_new_projection(db_session, monkeypatch):
    original = svc.rebuild_position
    def fail_after_projection(*args):
        original(*args)
        raise RuntimeError("after writes")
    monkeypatch.setattr(svc, "rebuild_position", fail_after_projection)
    with pytest.raises(RuntimeError):
        buy(db_session, "1")
    with Session(db_session.get_bind()) as fresh:
        assert list(fresh.scalars(select(Position))) == []
        assert list(fresh.scalars(select(PositionTransaction))) == []


def test_failed_correction_rolls_back_staged_replay(db_session, monkeypatch):
    buy(db_session, "10")
    buy(db_session, "10", "20", day=1)
    sell(db_session, "5", "30", day=2)
    second_buy = next(t for t in svc.list_transactions(db_session, "IREN", "BUY") if t.price_per_share == D("20"))
    original = svc.rebuild_position
    def fail_after_replay(*args):
        original(*args)
        args[0].flush()
        raise RuntimeError("after replay flush")
    monkeypatch.setattr(svc, "rebuild_position", fail_after_replay)
    with pytest.raises(RuntimeError):
        svc.delete_transaction(db_session, second_buy.id)
    with Session(db_session.get_bind()) as fresh:
        assert svc.get_position_by_ticker(fresh, "IREN").shares == D("15")
        assert svc.list_transactions(fresh, "IREN", "SELL")[0].cost_basis_total == D("75")
        assert len(svc.list_transactions(fresh)) == 3


def test_timezone_offset_is_normalized_before_sqlite_storage(db_session):
    local = timezone(timedelta(hours=-7))
    svc.buy_shares(db_session, "IREN", PositionBuy(quantity=D("10"), price_per_share=D("10"), transaction_date=datetime(2026, 9, 18, 15, tzinfo=local)))
    with Session(db_session.get_bind(), expire_on_commit=False) as fresh:
        entry = svc.list_transactions(fresh)[0]
        assert svc._as_aware(entry.transaction_date) == datetime(2026, 9, 18, 22, tzinfo=timezone.utc)
        sale = svc.sell_shares(fresh, "IREN", PositionSell(quantity=D("1"), price_per_share=D("11"), transaction_date=datetime(2026, 9, 18, 23, tzinfo=timezone.utc)))
        assert sale.shares == D("9")


@pytest.mark.parametrize("schema", [PositionBuy, PositionSell])
@pytest.mark.parametrize("field", ["quantity", "price_per_share", "fees"])
def test_excess_precision_is_rejected(schema, field):
    payload = {"quantity": "1", "price_per_share": "10", "fees": "0"}
    payload[field] = "0.0000001"
    with pytest.raises(ValidationError):
        schema(**payload)


def test_patch_rejects_ledger_derived_fields():
    for payload in ({"shares": "2"}, {"purchase_price": "5"}, {"purchase_date": "2026-09-01"}):
        with pytest.raises(ValidationError):
            PositionUpdate(**payload)


def test_concurrent_sqlite_sells_cannot_oversell(db_session):
    buy(db_session, "100")
    engine = db_session.get_bind()
    barrier = Barrier(2)
    def trade():
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            barrier.wait()
            try:
                sell(db, "80", "11")
                return "sold"
            except svc.PositionError:
                return "rejected"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: trade(), range(2)))
    assert sorted(results) == ["rejected", "sold"]
    with Session(engine) as fresh:
        assert svc.get_position_by_ticker(fresh, "IREN").shares == D("20")
        assert len(svc.list_transactions(fresh, "IREN", "SELL")) == 1


def test_concurrent_first_buys_share_one_projection(db_session):
    engine = db_session.get_bind()
    barrier = Barrier(2)
    def trade():
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            barrier.wait()
            return buy(db, "10").id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: trade(), range(2)))
    assert len(set(ids)) == 1
    with Session(engine) as fresh:
        assert svc.get_position_by_ticker(fresh, "IREN").shares == D("20")


def test_history_pages_do_not_skip_transactions(db_session):
    for i in range(501):
        db_session.add(PositionTransaction(ticker="IREN", transaction_type="BUY", quantity=D("1"), price_per_share=D("10"), fees=D("0"), transaction_date=NOW))
    db_session.commit()
    first = svc.list_transactions(db_session, limit=500)
    second = svc.list_transactions(db_session, limit=500, offset=500)
    assert len(first) == 500 and len(second) == 1
    assert len({t.id for t in first + second}) == 501
