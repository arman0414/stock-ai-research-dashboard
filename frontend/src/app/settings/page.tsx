"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, getHealth } from "@/lib/api";
import Disclaimer from "@/components/Disclaimer";

export default function SettingsPage() {
  const [status, setStatus] = useState<"checking" | "ok" | "unreachable">("checking");

  useEffect(() => {
    getHealth()
      .then(() => setStatus("ok"))
      .catch(() => setStatus("unreachable"));
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
