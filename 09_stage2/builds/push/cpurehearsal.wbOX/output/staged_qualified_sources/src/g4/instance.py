"""Typed, read-only adapter for the accepted G2 canonical instance."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Instance:
    tickers: tuple[str, ...]
    sectors: tuple[tuple[int, ...], ...]
    mu: tuple[float, ...]
    sigma: tuple[tuple[float, ...], ...]
    prices: tuple[float, ...]
    kappa_risk: float
    K: int
    C: int
    B: float


def load_instance(path: str | Path) -> Instance:
    """Load the accepted artifact without changing its keyed representation."""
    with Path(path).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    tickers = tuple(raw["universe"]["canonical_order"])
    sector_of = raw["universe"]["sector_of_ticker"]
    labels = tuple(raw["universe"]["sector_labels"])
    if len(tickers) != 20 or len(set(tickers)) != len(tickers):
        raise ValueError("canonical instance must contain 20 distinct tickers")
    sectors = tuple(tuple(i for i, ticker in enumerate(tickers) if sector_of[ticker] == label)
                    for label in labels)
    if tuple(sorted(index for sector in sectors for index in sector)) != tuple(range(20)):
        raise ValueError("sector map must partition the canonical order")
    return Instance(
        tickers=tickers,
        sectors=sectors,
        mu=tuple(float(raw["mu_by_ticker"][ticker]) for ticker in tickers),
        sigma=tuple(tuple(float(raw["Sigma_by_ticker"][i][j]) for j in tickers) for i in tickers),
        prices=tuple(float(raw["p_by_ticker"][ticker]) for ticker in tickers),
        kappa_risk=float(raw["kappa_risk"]["value"]),
        K=int(raw["K"]),
        C=int(raw["C"]),
        B=float(raw["B"]),
    )
