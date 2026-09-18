import type { NewsArticle, NewsRefreshResult, SentimentSummary } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { EmptyState } from "./StatusStates";

const PROVIDER_NAMES: Record<string, string> = {
  yahoo_rss: "Yahoo",
  finnhub: "Finnhub",
  alpha_vantage: "Alpha Vantage",
};

const PROVIDER_LABELS_FOR = (providers: string[] | undefined) =>
  (providers ?? []).map((p) => PROVIDER_NAMES[p] ?? p).join(" • ");

const SENTIMENT_STYLES: Record<string, string> = {
  POSITIVE: "bg-green-100 text-green-700",
  NEGATIVE: "bg-red-100 text-red-700",
  NEUTRAL: "bg-gray-100 text-gray-600",
};

export default function NewsList({
  articles,
  sentiment,
  onRefresh,
  refreshing = false,
  refreshResult,
}: {
  articles: NewsArticle[];
  sentiment: SentimentSummary | null;
  onRefresh?: () => void;
  refreshing?: boolean;
  refreshResult?: NewsRefreshResult | null;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-900">Latest News</h3>
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {refreshing ? "Refreshing..." : "Refresh News"}
          </button>
        )}
      </div>

      {sentiment && (
        <div className="mt-2">
          <div className="flex items-baseline gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">News Mood</p>
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${SENTIMENT_STYLES[sentiment.sentiment_direction] ?? SENTIMENT_STYLES.NEUTRAL}`}>
              {sentiment.sentiment_direction}
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            {sentiment.articles_7d} relevant recent {sentiment.articles_7d === 1 ? "article" : "articles"}
            {PROVIDER_LABELS_FOR(sentiment.providers) && ` · Sources: ${PROVIDER_LABELS_FOR(sentiment.providers)}`}
          </p>
          {sentiment.last_news_refresh && (
            <p className="mt-0.5 text-[11px] text-gray-400">Last news update: {formatDateTime(sentiment.last_news_refresh)}</p>
          )}
        </div>
      )}

      {sentiment && (
        <div className="mt-2 grid grid-cols-3 gap-2 text-center text-sm">
          <SentimentCount label="Positive" count={sentiment.positive} className="bg-green-50 text-green-700" />
          <SentimentCount label="Neutral" count={sentiment.neutral} className="bg-gray-50 text-gray-600" />
          <SentimentCount label="Negative" count={sentiment.negative} className="bg-red-50 text-red-700" />
        </div>
      )}

      {sentiment && sentiment.excluded_unrelated > 0 && (
        <details className="mt-2 text-xs text-gray-500">
          <summary className="cursor-pointer text-gray-400 hover:text-gray-600">Details</summary>
          <p className="mt-1">
            Excluded as unrelated: {sentiment.excluded_unrelated}. Only articles that mention the company are counted, so
            broad market stories do not move the mood.
          </p>
        </details>
      )}

      {refreshResult && (
        <div className="mt-2 rounded-md bg-gray-50 p-2 text-xs text-gray-600">
          <p>Unique new articles saved: {refreshResult.articles_created}</p>
          <p>
            {refreshResult.providers.map((provider) => `${provider.provider}: ${provider.status === "ok" ? `${provider.articles_received} received` : provider.status}`).join(" · ")}
          </p>
        </div>
      )}

      {articles.length === 0 ? (
        <div className="mt-3">
          <EmptyState title="No recent news available." />
        </div>
      ) : (
        <ul className="mt-3 space-y-3">
          {articles.map((article) => (
            <li key={article.id} className="rounded-lg border border-gray-100 p-3">
              <div className="flex items-start justify-between gap-2">
                {article.url ? (
                  <a href={article.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-gray-900 hover:underline">
                    {article.headline}
                  </a>
                ) : (
                  <p className="text-sm font-medium text-gray-900">{article.headline}</p>
                )}
                {article.sentiment && (
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${SENTIMENT_STYLES[article.sentiment.label] ?? SENTIMENT_STYLES.NEUTRAL}`}>
                    {article.sentiment.label}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-gray-400">
                {article.source} · {formatDateTime(article.published_at)}
                {(article.provider_sources ?? []).length > 1 && ` · via ${article.provider_sources.join(" + ")}`}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SentimentCount({ label, count, className }: { label: string; count: number; className: string }) {
  return (
    <div className={`rounded-md py-2 ${className}`}>
      <p className="text-lg font-semibold">{count}</p>
      <p className="text-[10px] uppercase tracking-wide">{label}</p>
    </div>
  );
}
