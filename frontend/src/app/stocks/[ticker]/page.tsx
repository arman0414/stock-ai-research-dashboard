"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getNews, getPredictionHistory, getPredictionPerformance, getPriceHistory, getSentimentSummary, getStockAnalysis, getStockDetail } from "@/lib/api";
import type { NewsArticle, PredictionHistoryRecord, PriceBarPoint, PriceRange, SentimentSummary, StockAnalysis, StockDetail as StockDetailType, StockLivePerformance } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { formatDateTime, formatSignedPercent } from "@/lib/format";
import { useQuotes } from "@/lib/useQuotes";
import CurrentPrice from "@/components/CurrentPrice";
import PredictionCard from "@/components/PredictionCard";
import PriceChart from "@/components/PriceChart";
import StructurePanel from "@/components/StructurePanel";
import ExplanationPanel from "@/components/ExplanationPanel";
import MarketContextPanel from "@/components/MarketContextPanel";
import NewsList from "@/components/NewsList";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import ResearchChecklist from "@/components/ResearchChecklist";
import WhatDoesThisMean from "@/components/WhatDoesThisMean";
import LiveForecastPerformance from "@/components/LiveForecastPerformance";
import PredictionHistoryList from "@/components/PredictionHistoryList";
import { ErrorState, LoadingState } from "@/components/StatusStates";

export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const [ticker, setTicker] = useState<string | null>(null);
  const [detail, setDetail] = useState<StockDetailType | null>(null);
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceBarPoint[]>([]);
  const [range, setRange] = useState<PriceRange>("6M");
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [sentiment, setSentiment] = useState<SentimentSummary | null>(null);
  const [predictionHistory, setPredictionHistory] = useState<PredictionHistoryRecord[]>([]);
  const [livePerformance, setLivePerformance] = useState<StockLivePerformance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { quotes, refreshing: quoteRefreshing } = useQuotes(ticker ? [ticker] : []);
  // Bumped on every loadCore() call so a slower, earlier request (e.g. for a
  // ticker the user has since navigated away from) can tell it's no longer
  // the latest one and skip committing its result.
  const loadRequestRef = useRef(0);

  useEffect(() => {
    params.then((resolved) => setTicker(resolved.ticker.toUpperCase()));
  }, [params]);

  const loadCore = useCallback(async () => {
    if (!ticker) return;
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    setError(null);
    try {
      const [detailResult, analysisResult] = await Promise.all([getStockDetail(ticker), getStockAnalysis(ticker)]);
      if (requestId !== loadRequestRef.current) return;
      setDetail(detailResult);
      setAnalysis(analysisResult);
    } catch (err) {
      if (requestId !== loadRequestRef.current) return;
      setError(err instanceof ApiError ? err.message : "Could not load this stock.");
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    // `active` guards every setState below against a fetch for a PREVIOUS
    // ticker resolving late (e.g. after the user has already navigated to a
    // new stock): without it, a slow request for the old ticker could
    // overwrite state that now belongs to the new one.
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, setState happens after the await
    loadCore();
    getNews(ticker).then((result) => active && setNews(result)).catch(() => active && setNews([]));
    getSentimentSummary(ticker).then((result) => active && setSentiment(result)).catch(() => active && setSentiment(null));
    getPredictionHistory(ticker).then((result) => active && setPredictionHistory(result)).catch(() => active && setPredictionHistory([]));
    getPredictionPerformance(ticker).then((result) => active && setLivePerformance(result)).catch(() => active && setLivePerformance(null));
    return () => {
      active = false;
    };
  }, [loadCore, ticker]);

  useEffect(() => {
    if (!ticker) return;
    // Same staleness guard: a previous range's (or ticker's) price-history
    // fetch resolving after this effect re-ran must never overwrite the
    // chart with data for a range/ticker the user is no longer viewing.
    let active = true;
    getPriceHistory(ticker, range)
      .then((result) => active && setPriceHistory(result))
      .catch(() => active && setPriceHistory([]));
    return () => {
      active = false;
    };
  }, [ticker, range]);

  if (!ticker || loading) return <LoadingState label={`Loading ${ticker ?? "stock"}…`} />;
  if (error) return <ErrorState message={error} onRetry={loadCore} />;
  if (!detail || !analysis) return <ErrorState message="No data available for this stock yet." />;

  const primary = analysis.predictions[analysis.primary_research_horizon as "5d"];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{ticker}</h1>
          {detail.company_name && <p className="text-sm text-gray-500">{detail.company_name}</p>}
          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            <CurrentPrice quote={ticker ? quotes[ticker] : undefined} fallbackPrice={detail.latest_price} refreshing={quoteRefreshing} />
            {primary && <span className="text-sm font-medium text-gray-500">Predicted 5-Day Move: {formatSignedPercent(primary.regression.predicted_return)}</span>}
          </div>
          <p className="mt-1 text-xs text-gray-400">Last refresh: {formatDateTime(detail.last_refreshed_at)}</p>
        </div>
        <RunAnalysisButton
          ticker={ticker}
          onComplete={(updated) => {
            setAnalysis(updated);
            getPredictionHistory(ticker).then(setPredictionHistory).catch(() => undefined);
            getPredictionPerformance(ticker).then(setLivePerformance).catch(() => undefined);
          }}
        />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Forecast</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HORIZONS.map((horizon) => {
            const prediction = analysis.predictions[horizon];
            if (!prediction) return null;
            return <PredictionCard key={horizon} prediction={prediction} emphasized={horizon === analysis.primary_research_horizon} />;
          })}
        </div>
        <div className="mt-4">
          <WhatDoesThisMean />
        </div>
      </section>

      {primary && (
        <section>
          <ResearchChecklist prediction={primary} marketContext={analysis.market_context} sentiment={sentiment} />
        </section>
      )}

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Why The Model Sees This</h2>
        <ExplanationPanel explanation={analysis.explanation} />
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Price Chart</h2>
        <PriceChart data={priceHistory} support={primary?.setup.support} resistance={primary?.setup.resistance} range={range} onRangeChange={setRange} />
        <div className="mt-4 border-t border-gray-100 pt-4">
          <StructurePanel structure={analysis.structure} />
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <MarketContextPanel context={analysis.market_context} />
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <NewsList articles={news} sentiment={sentiment} />
      </section>

      {livePerformance && (
        <section className="rounded-xl border border-gray-200 bg-white p-4">
          <LiveForecastPerformance performance={livePerformance} />
        </section>
      )}

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Prediction History</h2>
        <PredictionHistoryList records={predictionHistory} />
      </section>
    </div>
  );
}
