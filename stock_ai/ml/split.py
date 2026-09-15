from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChronologicalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    purge_gap: int


def chronological_split(
    dataset: pd.DataFrame,
    train_size: float = 0.70,
    validation_size: float = 0.15,
    purge_gap: int = 0,
    date_column: str = "date",
) -> ChronologicalSplit:
    """Split by date order and drop a horizon-sized purge gap between sets."""
    if date_column not in dataset.columns:
        raise ValueError(f"Missing date column: {date_column}")
    if not 0 < train_size < 1:
        raise ValueError("train_size must be between 0 and 1")
    if not 0 < validation_size < 1:
        raise ValueError("validation_size must be between 0 and 1")
    if train_size + validation_size >= 1:
        raise ValueError("train_size + validation_size must be less than 1")
    if purge_gap < 0:
        raise ValueError("purge_gap cannot be negative")

    sorted_data = dataset.copy()
    sorted_data[date_column] = pd.to_datetime(sorted_data[date_column])
    sort_columns = ["ticker", date_column] if "ticker" in sorted_data.columns else [date_column]
    sorted_data = sorted_data.sort_values(sort_columns).reset_index(drop=True)

    unique_dates = pd.Index(sorted(sorted_data[date_column].dropna().unique()))
    if len(unique_dates) < 3:
        raise ValueError("At least three unique dates are required for chronological splitting")

    train_cut = int(len(unique_dates) * train_size)
    validation_cut = int(len(unique_dates) * (train_size + validation_size))

    train_dates = unique_dates[:train_cut]
    validation_dates = unique_dates[train_cut + purge_gap : validation_cut]
    test_dates = unique_dates[validation_cut + purge_gap :]

    if len(train_dates) == 0 or len(validation_dates) == 0 or len(test_dates) == 0:
        raise ValueError("Split produced an empty train, validation, or test set")

    return ChronologicalSplit(
        train=_rows_for_dates(sorted_data, date_column, train_dates),
        validation=_rows_for_dates(sorted_data, date_column, validation_dates),
        test=_rows_for_dates(sorted_data, date_column, test_dates),
        purge_gap=purge_gap,
    )


def _rows_for_dates(dataset: pd.DataFrame, date_column: str, dates: pd.Index) -> pd.DataFrame:
    return dataset[dataset[date_column].isin(dates)].sort_values([date_column, "ticker"] if "ticker" in dataset.columns else [date_column]).reset_index(drop=True)

