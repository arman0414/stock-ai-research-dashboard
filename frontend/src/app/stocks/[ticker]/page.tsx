"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getNews, getPriceHistory, getSentimentSummary, getStockAnalysis, getStockDetail } from "@/lib/api";
import type { NewsArticle, PriceBarPoint, PriceRange, SentimentSummary, StockAnalysis, StockDetail as StockDetailType } from "@/lib/types";
import { HORIZONS } from "@/lib/types";
import { formatCurrency, formatDateTime, formatSignedPercent } from "@/lib/format";
import PredictionCard from "@/components/PredictionCard";
import PriceChart from "@/components/PriceChart";
import StructurePanel from "@/components/StructurePanel";
import ExplanationPanel from "@/components/ExplanationPanel";
import MarketContextPanel from "@/components/MarketContextPanel";
import NewsList from "@/components/NewsList";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import ResearchSummaryPanel from "@/components/ResearchSummaryPanel";
import ResearchChecklist from "@/components/ResearchChecklist";
import { ErrorState, LoadingState } from "@/components/StatusStates";

export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const [ticker, setTicker] = useState<string | null>(null);
  const [detail, setDetail] = useState<StockDetailType | null>(null);
  const [analysis, setAnalysis] = useState<StockAnalysis | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceBarPoint[]>([]);
  const [range, setRange] = useState<PriceRange>("6M");
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [sentiment, setSentiment] = useState<SentimentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    params.then((resolved) => setTicker(resolved.ticker.toUpperCase()));
  }, [params]);

  const loadCore = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const [detailResult, analysisResult] = await Promise.all([getStockDetail(ticker), getStockAnalysis(ticker)]);
      setDetail(detailResult);
      setAnalysis(analysisResult);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this stock.");
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    if (!ticker) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount, setState happens after the await
    loadCore();
    getNews(ticker).then(setNews).catch(() => setNews([]));
    getSentimentSummary(ticker).then(setSentiment).catch(() => setSentiment(null));
  }, [loadCore, ticker]);

  useEffect(() => {
    if (!ticker) return;
    getPriceHistory(ticker, range).then(setPriceHistory).catch(() => setPriceHistory([]));
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
          <div className="mt-2 flex items-baseline gap-3">
            <p className="text-3xl font-semibold text-gray-900">{formatCurrency(detail.latest_price)}</p>
            {primary && <span className="text-sm font-medium text-gray-500">Predicted 5D move: {formatSignedPercent(primary.regression.predicted_return)}</span>}
          </div>
          <p className="mt-1 text-xs text-gray-400">Last refresh: {formatDateTime(detail.last_refreshed_at)}</p>
        </div>
        <RunAnalysisButton ticker={ticker} onComplete={setAnalysis} />
      </div>

      {primary && (
        <section className="space-y-4">
          <ResearchSummaryPanel prediction={primary} marketContext={analysis.market_context} sentiment={sentiment} structure={analysis.structure} />
          <ResearchChecklist prediction={primary} marketContext={analysis.market_context} sentiment={sentiment} />
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Forecast</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {HORIZONS.map((horizon) => {
            const prediction = analysis.predictions[horizon];
            if (!prediction) return null;
            return <PredictionCard key={horizon} prediction={prediction} emphasized={horizon === analysis.primary_research_horizon} />;
          })}
        </div>
      </section>

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
    </div>
  );
}
