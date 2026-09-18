"""Position tracking with a transaction ledger and realized P/L.

ACCOUNTING MODEL
----------------
Average-cost (not FIFO/lot-based), which suits a personal research dashboard:
a SELL realizes against the position's current weighted-average cost, and
selling never changes the average cost of what remains.

  BUY   new_avg = (old_qty*old_avg + qty*price + fees) / (old_qty + qty)
        -- buy fees are capitalised into cost basis
  SELL  cost_basis  = qty * avg_cost
        net_proceeds = qty * price - fees      -- sell fees reduce proceeds
        realized     = net_proceeds - cost_basis

THE LEDGER IS AUTHORITATIVE
---------------------------
`Position` is a projection of `PositionTransaction`. Every mutation rebuilds
the position by replaying its ledger (rebuild_position), so the two can never
drift apart, and a correction is just "change the ledger, replay".

CORRECTION STRATEGY (chosen approach)
-------------------------------------
Full replay, not reversal entries: delete_transaction() removes the row and
replays the whole ledger for that ticker, recomputing every later SELL's cost
basis and realized P/L from scratch. That keeps history honest -- removing a
mistaken buy correctly changes what the following sells realized -- at the
cost of those later rows' frozen values legitimately changing. Market-price
movement never triggers a replay; only an explicit ledger edit does.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_ai.models.market_data import PriceBar
from stock_ai.models.positions import (
    SOURCE_MANUAL,
    SOURCE_MIGRATION,
    TRANSACTION_BUY,
    TRANSACTION_SELL,
    Position,
    PositionTransaction,
)
from stock_ai.schemas.positions import PositionBuy, PositionCreate, PositionSell, PositionUpdate
from stock_ai.schemas.stocks import normalize_ticker

MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
PERCENT = Decimal("0.0001")


class PositionError(ValueError):
    """A user-correctable problem, surfaced as a 400 rather than a 500."""


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY)


def _rate(value: Decimal) -> Decimal:
    return Decimal(value).quantize(RATE)


def _percent(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PERCENT)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_positions(db: Session, include_closed: bool = False) -> list[Position]:
    query = select(Position).order_by(Position.ticker)
    rows = list(db.scalars(query))
    return rows if include_closed else [row for row in rows if row.is_open]


def get_position(db: Session, position_id: int) -> Position | None:
    return db.get(Position, position_id)


def get_position_by_ticker(db: Session, ticker: str) -> Position | None:
    return db.scalar(select(Position).where(Position.ticker == normalize_ticker(ticker)))


def list_transactions(
    db: Session,
    ticker: str | None = None,
    transaction_type: str | None = None,
    limit: int = 500,
) -> list[PositionTransaction]:
    """Newest first. `transaction_date` may be NULL for migrated holdings, so
    `created_at` is the stable tiebreaker and keeps ordering deterministic."""
    query = select(PositionTransaction)
    if ticker:
        query = query.where(PositionTransaction.ticker == normalize_ticker(ticker))
    if transaction_type:
        query = query.where(PositionTransaction.transaction_type == transaction_type.upper())
    query = query.order_by(
        PositionTransaction.transaction_date.desc().nullslast(),
        PositionTransaction.created_at.desc(),
        PositionTransaction.id.desc(),
    ).limit(limit)
    return list(db.scalars(query))


def latest_price_for(db: Session, ticker: str) -> Decimal | None:
    bar = db.scalar(select(PriceBar).where(PriceBar.ticker == normalize_ticker(ticker)).order_by(PriceBar.date.desc()).limit(1))
    return bar.close if bar else None


# ---------------------------------------------------------------------------
# Ledger replay -- the single source of truth for position state
# ---------------------------------------------------------------------------


def _as_aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for timezone=True columns;
    normalize so stored and freshly-built values stay comparable."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _ordered_ledger(db: Session, ticker: str) -> list[PositionTransaction]:
    """Chronological order. Rows with an unknown date sort first (they are
    migrated opening balances, which by definition predate manual activity)."""
    rows = list(db.scalars(select(PositionTransaction).where(PositionTransaction.ticker == normalize_ticker(ticker))))
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(rows, key=lambda t: (t.transaction_date is not None, _as_aware(t.transaction_date) or epoch, t.id))


def rebuild_position(db: Session, ticker: str) -> Position | None:
    """Replay the whole ledger for one ticker and rewrite its Position row.

    Recomputes each SELL's cost basis / realized P/L against the average cost
    at that point in the replayed sequence, and assigns cycle indexes. Callers
    must commit; this only stages changes so a caller can roll back cleanly.
    """
    normalized = normalize_ticker(ticker)
    ledger = _ordered_ledger(db, normalized)
    position = get_position_by_ticker(db, normalized)

    quantity = Decimal("0")
    total_cost = Decimal("0")
    cycle = 1
    cycle_realized = Decimal("0")
    opened_on: datetime | None = None
    closed_at: datetime | None = None
    started = False

    for entry in ledger:
        if entry.transaction_type == TRANSACTION_BUY:
            if quantity == 0:
                # A buy from flat starts a new cycle (the first one, or a
                # re-open after a full sell).
                if started:
                    cycle += 1
                started = True
                cycle_realized = Decimal("0")
                opened_on = _as_aware(entry.transaction_date)
                closed_at = None
            entry.cycle_index = cycle
            total_cost += Decimal(entry.quantity) * Decimal(entry.price_per_share) + Decimal(entry.fees or 0)
            quantity += Decimal(entry.quantity)
        else:
            if Decimal(entry.quantity) > quantity:
                raise PositionError(
                    f"Ledger for {normalized} sells more shares than were held at that point "
                    f"({entry.quantity} sold, {quantity} held)."
                )
            entry.cycle_index = cycle
            average_cost = (total_cost / quantity) if quantity else Decimal("0")
            cost_basis_total = _money(Decimal(entry.quantity) * average_cost)
            gross = Decimal(entry.quantity) * Decimal(entry.price_per_share)
            net_proceeds = _money(gross - Decimal(entry.fees or 0))
            realized = _money(net_proceeds - cost_basis_total)

            entry.cost_basis_per_share = _rate(average_cost)
            entry.cost_basis_total = cost_basis_total
            entry.sale_proceeds = net_proceeds
            entry.realized_profit_loss = realized
            entry.realized_profit_loss_pct = _percent(realized / cost_basis_total * 100) if cost_basis_total else Decimal("0")

            # Average cost is unchanged by a sale: remove exactly the basis sold.
            total_cost -= Decimal(entry.quantity) * average_cost
            quantity -= Decimal(entry.quantity)
            cycle_realized += realized
            if quantity == 0:
                total_cost = Decimal("0")
                closed_at = _as_aware(entry.transaction_date) or datetime.now(timezone.utc)

    average_cost = _rate(total_cost / quantity) if quantity > 0 else Decimal("0")

    if position is None:
        if not ledger:
            return None
        position = Position(
            ticker=normalized,
            shares=quantity,
            purchase_price=average_cost,
            purchase_date=(opened_on.date() if opened_on else datetime.now(timezone.utc).date()),
        )
        db.add(position)

    position.shares = quantity
    # Keep the last known average cost on a closed row so history reads sanely.
    position.purchase_price = average_cost if quantity > 0 else Decimal(position.purchase_price)
    position.realized_pl = cycle_realized
    position.cycle_index = cycle
    position.closed_at = closed_at if quantity == 0 else None
    if opened_on is not None:
        position.purchase_date = opened_on.date()

    for entry in ledger:
        entry.position_id = position.id
    return position


# ---------------------------------------------------------------------------
# Mutations -- each one is atomic: ledger + position, or neither
# ---------------------------------------------------------------------------


def buy_shares(db: Session, ticker: str, payload: PositionBuy) -> Position:
    normalized = normalize_ticker(ticker)
    try:
        entry = PositionTransaction(
            ticker=normalized,
            transaction_type=TRANSACTION_BUY,
            quantity=payload.quantity,
            price_per_share=payload.price_per_share,
            fees=payload.fees or Decimal("0"),
            transaction_date=payload.transaction_date or datetime.now(timezone.utc),
            notes=payload.notes,
            source=SOURCE_MANUAL,
        )
        db.add(entry)
        db.flush()
        position = rebuild_position(db, normalized)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(position)
    return position


def sell_shares(db: Session, ticker: str, payload: PositionSell) -> Position:
    normalized = normalize_ticker(ticker)
    position = get_position_by_ticker(db, normalized)
    owned = Decimal(position.shares) if position else Decimal("0")
    if payload.quantity > owned:
        # Short selling is out of scope: the message states what is actually held.
        raise PositionError(f"You currently own {_trim(owned)} shares of {normalized}.")

    try:
        entry = PositionTransaction(
            ticker=normalized,
            transaction_type=TRANSACTION_SELL,
            quantity=payload.quantity,
            price_per_share=payload.price_per_share,
            fees=payload.fees or Decimal("0"),
            transaction_date=payload.transaction_date or datetime.now(timezone.utc),
            notes=payload.notes,
            source=SOURCE_MANUAL,
        )
        db.add(entry)
        db.flush()
        position = rebuild_position(db, normalized)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(position)
    return position


def preview_sell(db: Session, ticker: str, quantity: Decimal, price_per_share: Decimal, fees: Decimal | None = None) -> dict:
    """What a sale would realize, computed by the same rules as the real one,
    so the UI preview can never disagree with what gets recorded."""
    normalized = normalize_ticker(ticker)
    position = get_position_by_ticker(db, normalized)
    owned = Decimal(position.shares) if position else Decimal("0")
    average_cost = Decimal(position.purchase_price) if position else Decimal("0")
    cost_basis_total = _money(quantity * average_cost)
    net_proceeds = _money(quantity * price_per_share - (fees or Decimal("0")))
    realized = _money(net_proceeds - cost_basis_total)
    return {
        "ticker": normalized,
        "shares_owned": owned,
        "quantity": quantity,
        "cost_basis_per_share": _rate(average_cost),
        "cost_basis_total": cost_basis_total,
        "sale_proceeds": net_proceeds,
        "realized_profit_loss": realized,
        "realized_profit_loss_pct": _percent(realized / cost_basis_total * 100) if cost_basis_total else Decimal("0"),
        "remaining_shares": owned - quantity,
        "exceeds_position": quantity > owned,
    }


def delete_transaction(db: Session, transaction_id: int) -> Position | None:
    """Correction path: drop a ledger row and replay everything after it."""
    entry = db.get(PositionTransaction, transaction_id)
    if entry is None:
        return None
    ticker = entry.ticker
    try:
        db.delete(entry)
        db.flush()
        position = rebuild_position(db, ticker)
        db.commit()
    except Exception:
        db.rollback()
        raise
    if position is not None:
        db.refresh(position)
    return position


# ---------------------------------------------------------------------------
# Legacy create/update/delete (kept for the existing "I Bought This Stock" flow)
# ---------------------------------------------------------------------------


def create_position(db: Session, payload: PositionCreate) -> Position:
    """Opening a tracked holding records a real BUY, so a position created
    through the old form still starts with a proper ledger."""
    normalized = payload.normalized_ticker()
    existing = get_position_by_ticker(db, normalized)
    try:
        entry = PositionTransaction(
            ticker=normalized,
            transaction_type=TRANSACTION_BUY,
            quantity=payload.shares,
            price_per_share=payload.purchase_price,
            fees=Decimal("0"),
            transaction_date=datetime.combine(payload.purchase_date, datetime.min.time(), tzinfo=timezone.utc),
            notes=payload.notes,
            source=SOURCE_MANUAL,
        )
        db.add(entry)
        db.flush()
        position = rebuild_position(db, normalized)
        if existing is None:
            position.my_target_price = payload.my_target_price
            position.stop_loss_price = payload.stop_loss_price
            position.notes = payload.notes
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(position)
    return position


def update_position(db: Session, position_id: int, payload: PositionUpdate) -> Position | None:
    """Edits the user's own annotations only.

    Quantity and cost basis are ledger-derived and deliberately NOT settable
    here -- changing what you own goes through buy/sell so history is kept.
    """
    position = get_position(db, position_id)
    if not position:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(position, field, value)
    db.commit()
    db.refresh(position)
    return position


def delete_position(db: Session, position_id: int, keep_history: bool = True) -> bool:
    """Stops tracking a position. History is preserved by default: the ledger
    rows survive and still appear in Transaction History and Closed Positions."""
    position = get_position(db, position_id)
    if not position:
        return False
    if not keep_history:
        for entry in db.scalars(select(PositionTransaction).where(PositionTransaction.ticker == position.ticker)):
            db.delete(entry)
    else:
        for entry in db.scalars(select(PositionTransaction).where(PositionTransaction.position_id == position.id)):
            entry.position_id = None
    db.delete(position)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate_legacy_positions(db: Session) -> dict:
    """Give pre-ledger positions a synthetic opening BUY.

    Financial values are copied verbatim from the existing row (quantity and
    per-share cost), so quantity, average cost and position value are provably
    unchanged. The date is the recorded purchase_date; nothing is invented.
    """
    created = 0
    skipped = 0
    for position in db.scalars(select(Position)):
        has_ledger = db.scalar(
            select(PositionTransaction.id).where(PositionTransaction.ticker == position.ticker).limit(1)
        )
        if has_ledger:
            skipped += 1
            continue
        db.add(
            PositionTransaction(
                position_id=position.id,
                ticker=position.ticker,
                transaction_type=TRANSACTION_BUY,
                quantity=position.shares,
                price_per_share=position.purchase_price,
                fees=Decimal("0"),
                transaction_date=(
                    datetime.combine(position.purchase_date, datetime.min.time(), tzinfo=timezone.utc)
                    if position.purchase_date
                    else None
                ),
                notes="Opening balance migrated from manual position entry.",
                source=SOURCE_MIGRATION,
                cycle_index=position.cycle_index or 1,
            )
        )
        created += 1
    db.commit()
    return {"opening_transactions_created": created, "positions_already_with_history": skipped}


# ---------------------------------------------------------------------------
# Derived views
# ---------------------------------------------------------------------------


def closed_positions(db: Session) -> list[dict]:
    """Completed cycles, grouped by (ticker, cycle). A cycle counts as closed
    only once its quantity returns to zero -- a partially sold holding stays
    open even though it has realized P/L."""
    rows = list(db.scalars(select(PositionTransaction).order_by(PositionTransaction.ticker)))
    grouped: dict[tuple[str, int], list[PositionTransaction]] = {}
    for entry in rows:
        grouped.setdefault((entry.ticker, entry.cycle_index or 1), []).append(entry)

    results: list[dict] = []
    for (ticker, cycle), entries in grouped.items():
        bought = sum((Decimal(e.quantity) for e in entries if e.transaction_type == TRANSACTION_BUY), Decimal("0"))
        sold = sum((Decimal(e.quantity) for e in entries if e.transaction_type == TRANSACTION_SELL), Decimal("0"))
        if bought == 0 or sold < bought:
            continue  # still open
        sells = [e for e in entries if e.transaction_type == TRANSACTION_SELL]
        buys = [e for e in entries if e.transaction_type == TRANSACTION_BUY]
        cost_basis = sum((Decimal(e.cost_basis_total or 0) for e in sells), Decimal("0"))
        proceeds = sum((Decimal(e.sale_proceeds or 0) for e in sells), Decimal("0"))
        realized = sum((Decimal(e.realized_profit_loss or 0) for e in sells), Decimal("0"))
        buy_dates = [_as_aware(e.transaction_date) for e in buys if e.transaction_date]
        sell_dates = [_as_aware(e.transaction_date) for e in sells if e.transaction_date]
        results.append(
            {
                "ticker": ticker,
                "cycle_index": cycle,
                "total_shares_sold": sold,
                "total_cost_basis": _money(cost_basis),
                "total_proceeds": _money(proceeds),
                "realized_profit_loss": _money(realized),
                "return_pct": _percent(realized / cost_basis * 100) if cost_basis else Decimal("0"),
                "first_buy_date": min(buy_dates).isoformat() if buy_dates else None,
                "final_sell_date": max(sell_dates).isoformat() if sell_dates else None,
            }
        )
    results.sort(key=lambda r: (r["final_sell_date"] or "", r["ticker"]), reverse=True)
    return results


def realized_pl_total(db: Session, ticker: str | None = None) -> Decimal:
    """Lifetime realized P/L -- from completed SELL transactions only.
    Unrealized movement never contributes here."""
    query = select(PositionTransaction).where(PositionTransaction.transaction_type == TRANSACTION_SELL)
    if ticker:
        query = query.where(PositionTransaction.ticker == normalize_ticker(ticker))
    return _money(sum((Decimal(e.realized_profit_loss or 0) for e in db.scalars(query)), Decimal("0")))


def portfolio_summary(db: Session, prices: dict[str, Decimal | None] | None = None) -> dict:
    """Portfolio value, open cost basis, unrealized and realized P/L.

    `prices` comes from the caller (the existing LatestQuote service); this
    function never fetches quotes itself and does not change quote behavior.
    """
    prices = prices or {}
    open_rows = list_positions(db)
    market_value = Decimal("0")
    cost_basis = Decimal("0")
    priced_cost_basis = Decimal("0")
    for position in open_rows:
        quantity = Decimal(position.shares)
        average_cost = Decimal(position.purchase_price)
        cost_basis += quantity * average_cost
        price = prices.get(position.ticker)
        if price is not None:
            market_value += quantity * Decimal(price)
            priced_cost_basis += quantity * average_cost

    unrealized = market_value - priced_cost_basis
    realized = realized_pl_total(db)
    return {
        "portfolio_value": _money(market_value),
        "open_cost_basis": _money(cost_basis),
        "unrealized_pl": _money(unrealized),
        "unrealized_pl_pct": _percent(unrealized / priced_cost_basis * 100) if priced_cost_basis else Decimal("0"),
        "realized_pl": realized,
        "total_pl": _money(unrealized + realized),
        "open_position_count": len(open_rows),
        "priced_position_count": sum(1 for p in open_rows if prices.get(p.ticker) is not None),
    }


def position_to_dict(db: Session, position: Position) -> dict:
    """Serializes a position with its ledger-derived extras."""
    return {
        "id": position.id,
        "ticker": position.ticker,
        "shares": position.shares,
        "purchase_price": position.purchase_price,
        "average_cost": position.purchase_price,
        "total_cost_basis": position.total_cost_basis,
        "purchase_date": position.purchase_date,
        "my_target_price": position.my_target_price,
        "stop_loss_price": position.stop_loss_price,
        "notes": position.notes,
        "realized_pl": _money(Decimal(position.realized_pl or 0)),
        "lifetime_realized_pl": realized_pl_total(db, position.ticker),
        "cycle_index": position.cycle_index,
        "is_open": position.is_open,
        "closed_at": position.closed_at,
        "created_at": position.created_at,
        "updated_at": position.updated_at,
    }


def transaction_to_dict(entry: PositionTransaction) -> dict:
    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "transaction_type": entry.transaction_type,
        "quantity": entry.quantity,
        "price_per_share": entry.price_per_share,
        "fees": entry.fees,
        "transaction_date": entry.transaction_date,
        "notes": entry.notes,
        "source": entry.source,
        "cycle_index": entry.cycle_index,
        "cost_basis_per_share": entry.cost_basis_per_share,
        "cost_basis_total": entry.cost_basis_total,
        "sale_proceeds": entry.sale_proceeds,
        "realized_profit_loss": entry.realized_profit_loss,
        "realized_profit_loss_pct": entry.realized_profit_loss_pct,
        "created_at": entry.created_at,
    }


def _trim(value: Decimal) -> str:
    """Renders 100.000000 as "100" so validation messages read naturally."""
    normalized = Decimal(value).normalize()
    return format(normalized, "f")
