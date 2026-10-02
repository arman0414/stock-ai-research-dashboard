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
from decimal import Decimal, ROUND_HALF_EVEN

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
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_EVEN)


def _rate(value: Decimal) -> Decimal:
    return Decimal(value).quantize(RATE, rounding=ROUND_HALF_EVEN)


def _percent(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PERCENT, rounding=ROUND_HALF_EVEN)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_positions(db: Session, include_closed: bool = False) -> list[Position]:
    query = select(Position).order_by(Position.ticker)
    rows = list(db.scalars(query))
    return [row for row in rows if row.is_tracked and (include_closed or row.is_open)]


def get_position(db: Session, position_id: int) -> Position | None:
    return db.get(Position, position_id)


def get_position_by_ticker(db: Session, ticker: str) -> Position | None:
    return db.scalar(select(Position).where(Position.ticker == normalize_ticker(ticker)))


def list_transactions(
    db: Session,
    ticker: str | None = None,
    transaction_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
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
    ).offset(offset).limit(limit)
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


def _calculate_ledger(ledger: list[PositionTransaction]) -> dict:
    """Pure replay used by both persistence and dated previews.

    Keep the exact weighted average separate from rounded capital allocations.
    Cumulative rounding assigns residual cents without changing the average.
    """
    quantity = Decimal("0")
    total_cost = Decimal("0")
    capital = Decimal("0")
    allocated = Decimal("0")
    exact_allocated = Decimal("0")
    cycle = 0
    cycle_realized = Decimal("0")
    opened_on = None
    closed_at = None
    results = []
    for entry in ledger:
        qty = Decimal(entry.quantity)
        if qty <= 0 or Decimal(entry.price_per_share) <= 0:
            raise PositionError("Ledger quantities and prices must be positive.")
        fields = {}
        if entry.transaction_type == TRANSACTION_BUY:
            if quantity == 0:
                cycle += 1
                cycle_realized = Decimal("0")
                capital = allocated = exact_allocated = Decimal("0")
                opened_on = _as_aware(entry.transaction_date)
                closed_at = None
            purchase_cost = qty * Decimal(entry.price_per_share) + Decimal(entry.fees or 0)
            total_cost += purchase_cost
            capital += purchase_cost
            quantity += qty
        elif entry.transaction_type == TRANSACTION_SELL:
            if qty > quantity:
                raise PositionError(
                    f"Ledger for {entry.ticker} sells more shares than were held at that point "
                    f"({entry.quantity} sold, {quantity} held)."
                )
            average = total_cost / quantity
            exact_basis = qty * average
            exact_allocated += exact_basis
            basis = (_money(capital) - allocated) if qty == quantity else (_money(exact_allocated) - allocated)
            proceeds = _money(qty * Decimal(entry.price_per_share) - Decimal(entry.fees or 0))
            realized = _money(proceeds - basis)
            fields = {
                "cost_basis_per_share": _rate(average),
                "cost_basis_total": basis,
                "sale_proceeds": proceeds,
                "realized_profit_loss": realized,
                "realized_profit_loss_pct": _percent(realized / basis * 100) if basis else Decimal("0"),
            }
            total_cost -= exact_basis
            allocated += basis
            quantity -= qty
            cycle_realized += realized
            if quantity == 0:
                total_cost = Decimal("0")
                closed_at = _as_aware(entry.transaction_date)
        else:
            raise PositionError(f"Unknown transaction type: {entry.transaction_type}")
        results.append((entry, {"cycle_index": cycle, **fields}))
    return {
        "quantity": quantity,
        "average_cost": _rate(total_cost / quantity) if quantity else Decimal("0"),
        "remaining_cost_basis": _money(capital) - allocated,
        "cycle_index": cycle or 1,
        "realized_pl": cycle_realized,
        "opened_on": opened_on,
        "closed_at": closed_at,
        "results": results,
    }


def rebuild_position(db: Session, ticker: str) -> Position | None:
    """Stage the projection and sale audit fields; caller commits atomically."""
    normalized = normalize_ticker(ticker)
    ledger = _ordered_ledger(db, normalized)
    position = get_position_by_ticker(db, normalized)
    state = _calculate_ledger(ledger)
    if position is None:
        if not ledger:
            return None
        position = Position(
            ticker=normalized, shares=state["quantity"],
            purchase_price=state["average_cost"],
            purchase_date=state["opened_on"].date() if state["opened_on"] else datetime.now(timezone.utc).date(),
        )
        db.add(position)
        db.flush()  # assign the ID before linking the first ledger entry
    position.shares = state["quantity"]
    if state["quantity"]:
        position.purchase_price = state["average_cost"]
    position.remaining_cost_basis = state["remaining_cost_basis"]
    position.realized_pl = state["realized_pl"]
    position.cycle_index = state["cycle_index"]
    position.closed_at = state["closed_at"]
    if state["opened_on"] is not None:
        position.purchase_date = state["opened_on"].date()
    for entry, fields in state["results"]:
        entry.position_id = position.id
        for field, value in fields.items():
            setattr(entry, field, value)
    return position


def _lock_ledger(db: Session) -> None:
    """Serialize SQLite ledger writers before reading the current projection."""
    if db.get_bind().dialect.name == "sqlite":
        connection = db.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def _ensure_opening_balance(db: Session, ticker: str) -> None:
    # Also protects service callers that have not gone through app startup.
    migrate_legacy_positions(db, ticker=ticker, commit=False)


# ---------------------------------------------------------------------------
# Mutations -- each one is atomic: ledger + position, or neither
# ---------------------------------------------------------------------------


def buy_shares(db: Session, ticker: str, payload: PositionBuy) -> Position:
    normalized = normalize_ticker(ticker)
    try:
        _lock_ledger(db)
        _ensure_opening_balance(db, normalized)
        entry = PositionTransaction(
            ticker=normalized,
            transaction_type=TRANSACTION_BUY,
            quantity=payload.quantity,
            price_per_share=payload.price_per_share,
            fees=payload.fees or Decimal("0"),
            transaction_date=_as_aware(payload.transaction_date) or datetime.now(timezone.utc),
            notes=payload.notes,
            source=SOURCE_MANUAL,
        )
        db.add(entry)
        db.flush()
        position = rebuild_position(db, normalized)
        position.is_tracked = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(position)
    return position


def sell_shares(db: Session, ticker: str, payload: PositionSell) -> Position:
    normalized = normalize_ticker(ticker)
    try:
        _lock_ledger(db)
        _ensure_opening_balance(db, normalized)
        position = get_position_by_ticker(db, normalized)
        owned = Decimal(position.shares) if position else Decimal("0")
        if payload.quantity > owned:
            raise PositionError(f"You currently own {_trim(owned)} shares of {normalized}.")
        entry = PositionTransaction(
            ticker=normalized,
            transaction_type=TRANSACTION_SELL,
            quantity=payload.quantity,
            price_per_share=payload.price_per_share,
            fees=payload.fees or Decimal("0"),
            transaction_date=_as_aware(payload.transaction_date) or datetime.now(timezone.utc),
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


def preview_sell(
    db: Session, ticker: str, quantity: Decimal, price_per_share: Decimal,
    fees: Decimal | None = None, transaction_date: datetime | None = None,
) -> dict:
    """Replay a hypothetical sale without changing any persistent row."""
    payload = PositionSell(quantity=quantity, price_per_share=price_per_share,
                           fees=fees or Decimal("0"), transaction_date=transaction_date)
    normalized = normalize_ticker(ticker)
    ledger = _ordered_ledger(db, normalized)
    position = get_position_by_ticker(db, normalized)
    # Preview an unmigrated position without writing an opening balance.
    if not ledger and position and position.shares > 0:
        ledger = [PositionTransaction(id=0, ticker=normalized, transaction_type=TRANSACTION_BUY,
            quantity=position.shares, price_per_share=position.purchase_price, fees=Decimal("0"),
            transaction_date=datetime.combine(position.purchase_date, datetime.min.time(), tzinfo=timezone.utc))]
    owned = _calculate_ledger(ledger)["quantity"]
    candidate = PositionTransaction(id=max((e.id for e in ledger), default=0) + 1,
        ticker=normalized, transaction_type=TRANSACTION_SELL,
        quantity=payload.quantity, price_per_share=payload.price_per_share, fees=payload.fees,
        transaction_date=payload.transaction_date or datetime.now(timezone.utc))
    ordered = sorted([*ledger, candidate], key=lambda e: (
        e.transaction_date is not None,
        _as_aware(e.transaction_date) or datetime.min.replace(tzinfo=timezone.utc), e.id))
    try:
        state = _calculate_ledger(ordered)
    except PositionError as exc:
        return {"ticker": normalized, "shares_owned": owned, "quantity": quantity,
                "remaining_shares": owned - quantity, "exceeds_position": True,
                "error": str(exc)}
    fields = next(fields for entry, fields in state["results"] if entry is candidate)
    return {"ticker": normalized, "shares_owned": owned, "quantity": quantity,
            "remaining_shares": state["quantity"], "exceeds_position": False, **fields}


def delete_transaction(db: Session, transaction_id: int) -> Position | None:
    """Correction path: drop a ledger row and replay everything after it."""
    try:
        _lock_ledger(db)
        entry = db.get(PositionTransaction, transaction_id)
        if entry is None:
            return None
        ticker = entry.ticker
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
    try:
        _lock_ledger(db)
        _ensure_opening_balance(db, normalized)
        existing = get_position_by_ticker(db, normalized)
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
        position.is_tracked = True
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
    """Hide tracking without erasing the ledger, projection or annotations."""
    try:
        _lock_ledger(db)
        position = get_position(db, position_id)
        if not position or (keep_history and not position.is_tracked):
            return False
        if keep_history:
            position.is_tracked = False
        else:
            for entry in db.scalars(select(PositionTransaction).where(PositionTransaction.ticker == position.ticker)):
                db.delete(entry)
            db.delete(position)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate_legacy_positions(db: Session, ticker: str | None = None, commit: bool = True) -> dict:
    """Commit a migration atomically, or stage it inside a caller's transaction."""
    try:
        if commit:
            _lock_ledger(db)
        report = _migrate_legacy_positions(db, ticker)
        if commit:
            db.commit()
        return report
    except Exception:
        if commit:
            db.rollback()
        raise


def _migrate_legacy_positions(db: Session, ticker: str | None = None) -> dict:
    """Give pre-ledger positions a synthetic opening BUY.

    Multiple legacy rows for one ticker become one aggregate projection,
    retaining each opening balance and all annotations.

    Financial values are copied verbatim from the existing row (quantity and
    per-share cost), so quantity, average cost and position value are provably
    unchanged. The date is the recorded purchase_date; nothing is invented.
    """
    created = 0
    skipped = 0
    query = select(Position)
    if ticker:
        query = query.where(Position.ticker == normalize_ticker(ticker))
    groups: dict[str, list[Position]] = {}
    for position in db.scalars(query.order_by(Position.id)):
        groups.setdefault(position.ticker, []).append(position)
    for symbol, positions in groups.items():
        has_ledger = db.scalar(select(PositionTransaction.id).where(PositionTransaction.ticker == symbol).limit(1))
        if has_ledger:
            skipped += len(positions)
        else:
            for position in positions:
                if position.shares <= 0:
                    continue
                db.add(PositionTransaction(
                    position_id=position.id, ticker=symbol, transaction_type=TRANSACTION_BUY,
                    quantity=position.shares, price_per_share=position.purchase_price, fees=Decimal("0"),
                    transaction_date=(datetime.combine(position.purchase_date, datetime.min.time(), tzinfo=timezone.utc)
                                      if position.purchase_date else None),
                    notes="Opening balance migrated from manual position entry.",
                    source=SOURCE_MIGRATION, cycle_index=position.cycle_index or 1,
                ))
                created += 1
        db.flush()
        if len(positions) > 1:
            canonical = positions[0]
            # Retain annotations from additional legacy rows as text rather than
            # silently choosing one target/stop or discarding their notes.
            preserved = [canonical.notes] if canonical.notes else []
            for duplicate in positions[1:]:
                preserved.append(f"Legacy position {duplicate.id}: target={duplicate.my_target_price}; "
                                 f"stop={duplicate.stop_loss_price}; notes={duplicate.notes or ''}")
            canonical.notes = "\n".join(preserved) or None
            canonical.is_tracked = any(position.is_tracked for position in positions)
            rebuild_position(db, symbol)
            db.flush()  # link all ledger entries to the canonical row first
            for duplicate in positions[1:]:
                db.delete(duplicate)
            db.flush()
    db.flush()
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
        cost_basis += position.total_cost_basis
        price = prices.get(position.ticker)
        if price is not None:
            market_value += quantity * Decimal(price)
            priced_cost_basis += position.total_cost_basis

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
