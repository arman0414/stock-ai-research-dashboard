"""Position transaction ledger, average-cost accounting, and realized P/L."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from stock_ai.models.positions import SOURCE_MIGRATION, Position, PositionTransaction
from stock_ai.schemas.positions import PositionBuy, PositionCreate, PositionSell
from stock_ai.services import positions as svc

D = Decimal
NOW = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def buy(db, ticker="IREN", qty="100", price="30", fees="0", when=NOW, notes=None):
    return svc.buy_shares(db, ticker, PositionBuy(quantity=D(qty), price_per_share=D(price), fees=D(fees), transaction_date=when, notes=notes))


def sell(db, ticker="IREN", qty="50", price="45", fees="0", when=NOW, notes=None):
    return svc.sell_shares(db, ticker, PositionSell(quantity=D(qty), price_per_share=D(price), fees=D(fees), transaction_date=when, notes=notes))


# ---------------------------------------------------------------------------
# Buying
# ---------------------------------------------------------------------------


def test_first_buy_opens_position(db_session):
    position = buy(db_session, qty="100", price="30")
    assert position.shares == D("100")
    assert position.purchase_price == D("30")
    assert position.is_open is True
    assert position.total_cost_basis == D("3000.00")

    ledger = svc.list_transactions(db_session, "IREN")
    assert len(ledger) == 1
    assert ledger[0].transaction_type == "BUY"


def test_buy_more_uses_weighted_average_cost(db_session):
    """Spec example: 100 @ $30 then 50 @ $36 -> 150 shares @ $32."""
    buy(db_session, qty="100", price="30")
    position = buy(db_session, qty="50", price="36", when=NOW + timedelta(days=1))
    assert position.shares == D("150")
    assert position.purchase_price == D("32")


def test_buy_does_not_replace_earlier_buys(db_session):
    buy(db_session, qty="100", price="30")
    buy(db_session, qty="50", price="36", when=NOW + timedelta(days=1))
    buys = svc.list_transactions(db_session, "IREN", "BUY")
    assert len(buys) == 2
    assert sorted(D(b.quantity) for b in buys) == [D("50"), D("100")]


def test_buy_fees_are_capitalised_into_cost_basis(db_session):
    position = buy(db_session, qty="100", price="30", fees="50")
    # (100*30 + 50) / 100 = 30.50
    assert position.purchase_price == D("30.50")


# ---------------------------------------------------------------------------
# Selling
# ---------------------------------------------------------------------------


def test_partial_sell_realizes_profit_and_keeps_position_open(db_session):
    """Spec example: 150 @ $32, sell 50 @ $45 -> +$650 (+40.625%)."""
    buy(db_session, qty="100", price="30")
    buy(db_session, qty="50", price="36", when=NOW + timedelta(days=1))
    position = sell(db_session, qty="50", price="45", when=NOW + timedelta(days=2))

    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    assert entry.cost_basis_total == D("1600.00")
    assert entry.sale_proceeds == D("2250.00")
    assert entry.realized_profit_loss == D("650.00")
    assert entry.realized_profit_loss_pct == D("40.6250")

    assert position.shares == D("100")
    assert position.purchase_price == D("32"), "average cost must not change on a sale"
    assert position.is_open is True
    assert position.closed_at is None


def test_realized_loss(db_session):
    buy(db_session, qty="100", price="50")
    sell(db_session, qty="40", price="35", when=NOW + timedelta(days=1))
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    assert entry.cost_basis_total == D("2000.00")
    assert entry.sale_proceeds == D("1400.00")
    assert entry.realized_profit_loss == D("-600.00")
    assert entry.realized_profit_loss_pct == D("-30.0000")


def test_sell_fees_reduce_net_proceeds(db_session):
    """Spec example: gross $2,250 with a $2 fee -> net $2,248."""
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", fees="2", when=NOW + timedelta(days=1))
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    assert entry.sale_proceeds == D("2248.00")
    assert entry.realized_profit_loss == D("648.00")


def test_full_sell_closes_position_but_keeps_history(db_session):
    buy(db_session, qty="150", price="32")
    position = sell(db_session, qty="150", price="45", when=NOW + timedelta(days=1))

    assert position.shares == D("0")
    assert position.is_open is False
    assert position.closed_at is not None
    assert svc.list_positions(db_session) == [], "closed position must leave Open Positions"
    assert len(svc.list_transactions(db_session, "IREN")) == 2, "history must survive"


def test_multiple_partial_sells_accumulate_realized_pl(db_session):
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))
    position = sell(db_session, qty="50", price="40", when=NOW + timedelta(days=2))

    assert position.shares == D("50")
    # 650 + (2000 - 1600) = 1050
    assert svc.realized_pl_total(db_session, "IREN") == D("1050.00")
    assert D(position.realized_pl) == D("1050.00")


def test_cannot_sell_more_than_owned(db_session):
    buy(db_session, qty="100", price="30")
    with pytest.raises(svc.PositionError) as exc:
        sell(db_session, qty="120", price="45")
    assert "You currently own 100 shares of IREN." in str(exc.value)


def test_failed_sell_creates_no_transaction(db_session):
    buy(db_session, qty="100", price="30")
    with pytest.raises(svc.PositionError):
        sell(db_session, qty="120", price="45")
    assert len(svc.list_transactions(db_session, "IREN")) == 1
    assert svc.get_position_by_ticker(db_session, "IREN").shares == D("100")


def test_rollback_leaves_ledger_and_position_consistent(db_session, monkeypatch):
    """If the position rebuild fails mid-operation, neither side is written."""
    buy(db_session, qty="100", price="30")

    def _explode(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(svc, "rebuild_position", _explode)
    with pytest.raises(RuntimeError):
        sell(db_session, qty="10", price="45")

    assert len(svc.list_transactions(db_session, "IREN")) == 1, "no orphan SELL row"
    assert svc.get_position_by_ticker(db_session, "IREN").shares == D("100")


# ---------------------------------------------------------------------------
# History immutability + re-opening
# ---------------------------------------------------------------------------


def test_historical_sale_is_unchanged_when_quote_changes(db_session):
    from stock_ai.models.market_data import PriceBar

    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    frozen = (entry.price_per_share, entry.cost_basis_total, entry.sale_proceeds, entry.realized_profit_loss)

    # Market moves hard afterwards.
    db_session.add(PriceBar(ticker="IREN", date=NOW.date(), open=D("10"), high=D("10"), low=D("10"), close=D("10"), adjusted_close=D("10"), volume=1))
    db_session.commit()
    svc.portfolio_summary(db_session, {"IREN": D("10")})

    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    assert (entry.price_per_share, entry.cost_basis_total, entry.sale_proceeds, entry.realized_profit_loss) == frozen


def test_rebuy_after_close_starts_new_cycle_and_keeps_old_history(db_session):
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="150", price="45", when=NOW + timedelta(days=1))
    first_cycle_realized = svc.realized_pl_total(db_session, "IREN")

    position = buy(db_session, qty="10", price="50", when=NOW + timedelta(days=5))
    assert position.shares == D("10")
    assert position.purchase_price == D("50")
    assert position.cycle_index == 2
    assert position.is_open is True
    assert D(position.realized_pl) == D("0"), "new cycle starts with no realized P/L"
    # Previous cycle's realized P/L is untouched.
    assert svc.realized_pl_total(db_session, "IREN") == first_cycle_realized

    closed = svc.closed_positions(db_session)
    assert len(closed) == 1 and closed[0]["cycle_index"] == 1


def test_closed_position_totals(db_session):
    """Spec example: cost basis $4,800, proceeds $6,750, +$1,950 (+40.63%)."""
    buy(db_session, qty="100", price="30")
    buy(db_session, qty="50", price="36", when=NOW + timedelta(days=1))
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=2))
    sell(db_session, qty="100", price="45", when=NOW + timedelta(days=3))

    closed = svc.closed_positions(db_session)
    assert len(closed) == 1
    row = closed[0]
    assert row["ticker"] == "IREN"
    assert row["total_shares_sold"] == D("150")
    assert row["total_cost_basis"] == D("4800.00")
    assert row["total_proceeds"] == D("6750.00")
    assert row["realized_profit_loss"] == D("1950.00")
    assert row["return_pct"] == D("40.6250")
    assert row["first_buy_date"] is not None and row["final_sell_date"] is not None


def test_partially_sold_position_is_not_listed_as_closed(db_session):
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))
    assert svc.closed_positions(db_session) == []
    assert [p.ticker for p in svc.list_positions(db_session)] == ["IREN"]


# ---------------------------------------------------------------------------
# Ordering, filters, corrections
# ---------------------------------------------------------------------------


def test_transactions_are_newest_first(db_session):
    buy(db_session, qty="10", price="30", when=NOW)
    buy(db_session, qty="10", price="31", when=NOW + timedelta(days=2))
    buy(db_session, qty="10", price="32", when=NOW + timedelta(days=1))
    prices = [D(t.price_per_share) for t in svc.list_transactions(db_session, "IREN")]
    assert prices == [D("31"), D("32"), D("30")]


def test_transaction_filters(db_session):
    buy(db_session, qty="100", price="30")
    sell(db_session, qty="10", price="45", when=NOW + timedelta(days=1))
    buy(db_session, ticker="NVDA", qty="5", price="200", when=NOW + timedelta(days=2))

    assert len(svc.list_transactions(db_session)) == 3
    assert len(svc.list_transactions(db_session, ticker="IREN")) == 2
    assert len(svc.list_transactions(db_session, transaction_type="SELL")) == 1
    assert len(svc.list_transactions(db_session, ticker="NVDA", transaction_type="BUY")) == 1


def test_deleting_a_transaction_rebuilds_position_from_ledger(db_session):
    buy(db_session, qty="100", price="30")
    buy(db_session, qty="50", price="36", when=NOW + timedelta(days=1))
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=2))

    # Remove the second buy: average cost reverts to $30 and the sale's
    # realized P/L is recomputed against it rather than left stale.
    second_buy = next(t for t in svc.list_transactions(db_session, "IREN", "BUY") if D(t.price_per_share) == D("36"))
    position = svc.delete_transaction(db_session, second_buy.id)

    assert position.shares == D("50")
    assert position.purchase_price == D("30")
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    assert entry.cost_basis_total == D("1500.00")
    assert entry.realized_profit_loss == D("750.00")


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_legacy_position_migration_preserves_values(db_session):
    legacy = Position(ticker="IREN", shares=D("22"), purchase_price=D("43.11"), purchase_date=NOW.date(), my_target_price=D("46"))
    db_session.add(legacy)
    db_session.commit()
    before = (D(legacy.shares), D(legacy.purchase_price), legacy.purchase_date, legacy.my_target_price)

    report = svc.migrate_legacy_positions(db_session)
    assert report["opening_transactions_created"] == 1

    db_session.refresh(legacy)
    assert (D(legacy.shares), D(legacy.purchase_price), legacy.purchase_date, legacy.my_target_price) == before

    entry = svc.list_transactions(db_session, "IREN")[0]
    assert entry.source == SOURCE_MIGRATION
    assert D(entry.quantity) == D("22")
    assert D(entry.price_per_share) == D("43.11")


def test_migration_is_idempotent_and_skips_positions_with_history(db_session):
    buy(db_session, qty="100", price="30")
    report = svc.migrate_legacy_positions(db_session)
    assert report["opening_transactions_created"] == 0
    assert report["positions_already_with_history"] == 1
    assert len(svc.list_transactions(db_session, "IREN")) == 1


def test_unknown_transaction_date_stays_null_and_replays_first(db_session):
    """An unknown date stays unknown rather than being invented, and such a
    row replays before dated activity (it is an opening balance)."""
    db_session.add(
        PositionTransaction(
            ticker="MU", transaction_type="BUY", quantity=D("10"), price_per_share=D("5"),
            fees=D("0"), transaction_date=None, source=SOURCE_MIGRATION,
        )
    )
    db_session.commit()
    svc.rebuild_position(db_session, "MU")
    db_session.commit()

    entry = svc.list_transactions(db_session, "MU")[0]
    assert entry.transaction_date is None, "no date may be invented"

    buy(db_session, ticker="MU", qty="10", price="15", when=NOW)
    position = svc.get_position_by_ticker(db_session, "MU")
    # Undated opening balance replays first: (10*5 + 10*15) / 20 = 10
    assert position.shares == D("20")
    assert position.purchase_price == D("10")


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------


def test_portfolio_summary_separates_realized_and_unrealized(db_session):
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))

    summary = svc.portfolio_summary(db_session, {"IREN": D("45")})
    assert summary["portfolio_value"] == D("4500.00")  # 100 * 45
    assert summary["open_cost_basis"] == D("3200.00")  # 100 * 32
    assert summary["unrealized_pl"] == D("1300.00")
    assert summary["realized_pl"] == D("650.00")
    assert summary["total_pl"] == D("1950.00")
    # Realized P/L must not leak into unrealized and vice versa.
    assert summary["unrealized_pl"] != summary["realized_pl"]


def test_portfolio_summary_without_quotes_still_reports_cost_and_realized(db_session):
    buy(db_session, qty="150", price="32")
    sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))
    summary = svc.portfolio_summary(db_session, {})
    assert summary["open_cost_basis"] == D("3200.00")
    assert summary["realized_pl"] == D("650.00")
    assert summary["unrealized_pl"] == D("0.00")


def test_monetary_rounding_has_no_float_artifacts(db_session):
    """Awkward thirds must not surface as 649.999999997."""
    buy(db_session, qty="3", price="10.1")
    position = sell(db_session, qty="1", price="20.3", when=NOW + timedelta(days=1))
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]
    for value in (entry.cost_basis_total, entry.sale_proceeds, entry.realized_profit_loss):
        # 3 @ 10.10 gives an average of exactly 10.10, but the guard that
        # matters is that stored money equals its own 2dp rounding -- no
        # 649.999999997 style residue.
        assert Decimal(value) == Decimal(value).quantize(Decimal("0.01")), f"{value} carries sub-cent residue"
    assert Decimal(position.realized_pl) == Decimal(position.realized_pl).quantize(Decimal("0.01"))


def test_create_position_records_an_opening_buy(db_session):
    """The existing "I Bought This Stock" flow still produces a real ledger."""
    position = svc.create_position(
        db_session,
        PositionCreate(ticker="nvda", shares=D("10"), purchase_price=D("100"), purchase_date=NOW.date(), my_target_price=D("150")),
    )
    assert position.ticker == "NVDA"
    assert position.shares == D("10")
    entries = svc.list_transactions(db_session, "NVDA")
    assert len(entries) == 1 and entries[0].transaction_type == "BUY"


def test_update_position_cannot_change_quantity_or_cost(db_session):
    """Quantity/cost are ledger-derived; the edit form only touches annotations."""
    from stock_ai.schemas.positions import PositionUpdate

    position = buy(db_session, qty="100", price="30")
    assert "shares" not in PositionUpdate.model_fields
    assert "purchase_price" not in PositionUpdate.model_fields

    updated = svc.update_position(db_session, position.id, PositionUpdate(my_target_price=D("99")))
    assert updated.my_target_price == D("99")
    assert updated.shares == D("100")
    assert updated.purchase_price == D("30")


def test_sell_preview_matches_recorded_sale(db_session):
    buy(db_session, qty="150", price="32")
    preview = svc.preview_sell(db_session, "IREN", D("50"), D("45"), D("0"))
    position = sell(db_session, qty="50", price="45", when=NOW + timedelta(days=1))
    entry = svc.list_transactions(db_session, "IREN", "SELL")[0]

    assert preview["cost_basis_total"] == entry.cost_basis_total
    assert preview["sale_proceeds"] == entry.sale_proceeds
    assert preview["realized_profit_loss"] == entry.realized_profit_loss
    assert preview["remaining_shares"] == D(position.shares)
    assert preview["exceeds_position"] is False


def test_sell_preview_flags_oversell(db_session):
    buy(db_session, qty="100", price="30")
    preview = svc.preview_sell(db_session, "IREN", D("120"), D("45"))
    assert preview["exceeds_position"] is True
    assert preview["shares_owned"] == D("100")
