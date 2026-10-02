from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_ai.db.session import Base

TRANSACTION_BUY = "BUY"
TRANSACTION_SELL = "SELL"

SOURCE_MANUAL = "manual"
SOURCE_MIGRATION = "migration_opening_balance"


class Position(Base):
    """A manually-entered holding for the My Positions page -- CURRENT STATE only.

    No brokerage integration: shares/prices/dates are user-entered.
    `my_target_price`/`stop_loss_price` are the user's own targets and must
    never be confused with the model's predicted target price, which is
    computed fresh by the prediction service and never stored here.

    This row is a projection of the PositionTransaction ledger, which is the
    authoritative record. `shares` is the CURRENT quantity and
    `purchase_price` is the CURRENT weighted-average cost per share (both are
    recomputed by rebuilding from the ledger, never edited ad hoc). A fully
    sold position keeps its row with shares = 0 and `closed_at` set, so the
    user's target/stop/notes survive and the ticker can be re-opened later
    without erasing anything.
    """

    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_ticker", "ticker", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    my_target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    # Rounded capital not yet allocated to sales. The final sale receives any
    # residual cents, while the weighted average itself remains unchanged.
    remaining_cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    # Realized P/L accumulated during the CURRENT open cycle. Lifetime realized
    # P/L is derived from the ledger, never from this field.
    realized_pl: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default=text("0"))
    # Which open/close cycle this row is on. A cycle starts when quantity goes
    # from 0 to positive and ends when it returns to 0; re-buying a closed
    # ticker starts a new cycle and never rewrites the previous one.
    cycle_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def is_open(self) -> bool:
        return self.shares is not None and Decimal(self.shares) > 0

    @property
    def total_cost_basis(self) -> Decimal:
        if self.remaining_cost_basis is not None:
            return Decimal(self.remaining_cost_basis).quantize(Decimal("0.01"))
        return (Decimal(self.shares) * Decimal(self.purchase_price)).quantize(Decimal("0.01"))


class PositionTransaction(Base):
    """One immutable BUY or SELL entry in the position ledger.

    Financial fields on a SELL (cost basis, proceeds, realized P/L) are frozen
    at the moment the transaction is recorded and are never recomputed when
    market prices move. They only ever change if the ledger itself is edited,
    which goes through a full replay (see services.positions.rebuild_position).
    """

    __tablename__ = "position_transactions"
    __table_args__ = (
        Index("ix_position_transactions_ticker_date", "ticker", "transaction_date"),
        Index("ix_position_transactions_ticker_cycle", "ticker", "cycle_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id", ondelete="SET NULL"), nullable=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price_per_share: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"), server_default=text("0"))
    # Nullable on purpose: a migrated legacy holding with no known purchase
    # date keeps "unknown" rather than being given an invented date.
    transaction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default=SOURCE_MANUAL, server_default=text("'manual'"))
    cycle_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))

    # SELL-only audit fields, frozen at record time.
    cost_basis_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    cost_basis_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    sale_proceeds: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    realized_profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    realized_profit_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    position: Mapped[Position | None] = relationship()


def ensure_positions_schema(engine: Engine) -> None:
    """Back-fill new columns on an existing SQLite database.

    The project has no migration framework yet; create_all() handles fresh
    databases and this hook keeps the local file compatible without touching
    existing rows or their financial values.
    """
    if engine.dialect.name != "sqlite":
        return
    existing = {column["name"] for column in inspect(engine).get_columns("positions")}
    required = {
        "realized_pl": "NUMERIC(18, 6) NOT NULL DEFAULT 0",
        "cycle_index": "INTEGER NOT NULL DEFAULT 1",
        "closed_at": "DATETIME",
        "is_tracked": "BOOLEAN NOT NULL DEFAULT 1",
        "remaining_cost_basis": "NUMERIC(18, 6)",
    }
    with engine.begin() as connection:
        for column, ddl_type in required.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE positions ADD COLUMN {column} {ddl_type}"))
