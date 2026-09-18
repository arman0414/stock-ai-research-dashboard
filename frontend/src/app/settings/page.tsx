"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, getDailyRunStatus, getHealth, getNewsProviderStatus } from "@/lib/api";
import type { DailyRunStatus, NeverRunStatus, NewsProviderHealth } from "@/lib/types";
import Disclaimer from "@/components/Disclaimer";
import DailyRunStatusPanel from "@/components/DailyRunStatusPanel";

export default function SettingsPage() {
  const [status, setStatus] = useState<"checking" | "ok" | "unreachable">("checking");
  const [dailyRunStatus, setDailyRunStatus] = useState<DailyRunStatus | NeverRunStatus | null>(null);
  const [newsProviderHealth, setNewsProviderHealth] = useState<NewsProviderHealth | null>(null);

  useEffect(() => {
    getHealth()
      .then(() => setStatus("ok"))
      .catch(() => setStatus("unreachable"));
    getDailyRunStatus()
      .then(setDailyRunStatus)
      .catch(() => setDailyRunStatus(null));
    getNewsProviderStatus()
      .then(setNewsProviderHealth)
      .catch(() => setNewsProviderHealth(null));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-gray-900">Settings</h1>

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-gray-900">Backend Connection</h2>
        <dl className="mt-2 space-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-gray-400">API base URL</dt>
            <dd className="font-mono text-gray-900">{API_BASE_URL}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-400">Status</dt>
            <dd className={status === "ok" ? "font-medium text-green-700" : status === "unreachable" ? "font-medium text-red-700" : "text-gray-500"}>
              {status === "ok" ? "Connected" : status === "unreachable" ? "Unreachable" : "Checking…"}
            </dd>
          </div>
        </dl>
      </section>

      {dailyRunStatus && <DailyRunStatusPanel status={dailyRunStatus} />}

      {newsProviderHealth && (
        <section className="rounded-xl border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-900">News Providers</h2>
          <dl className="mt-3 space-y-2 text-sm">
            {newsProviderHealth.providers.map((provider) => (
              <div key={provider.provider} className="flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-2 first:border-t-0 first:pt-0">
                <dt className="font-medium text-gray-700">{provider.provider}</dt>
                <dd className={provider.available && provider.status !== "rate_limited" ? "text-green-700" : "text-amber-700"}>
                  {provider.available ? provider.status : "unavailable"}
                  {provider.last_news_refresh ? ` · ${new Date(provider.last_news_refresh).toLocaleString()}` : ""}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-gray-900">About This Dashboard</h2>
        <p className="mt-2 text-sm text-gray-600">
          This is a personal research dashboard for absolute stock direction and return predictions. It does not execute trades, connect to a
          brokerage, or guarantee outcomes. The 5-day horizon is currently the model&apos;s strongest and is treated as the primary research
          horizon; 10-day and 15-day horizons remain visible but are secondary.
        </p>
      </section>

      <section className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-gray-900">Disclaimer</h2>
        <div className="mt-2">
          <Disclaimer />
        </div>
      </section>
    </div>
  );
}
