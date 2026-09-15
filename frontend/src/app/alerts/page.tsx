"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, checkAlerts, deleteAlert } from "@/lib/api";
import type { AlertStatus } from "@/lib/types";
import AlertForm from "@/components/AlertForm";
import AlertCard from "@/components/AlertCard";
import { EmptyState, ErrorState, LoadingState } from "@/components/StatusStates";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setAlerts(await checkAlerts());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load alerts.");
    }
  }, []);

  useEffect(() => {
    // Standard fetch-on-mount: load() is async and only calls setState after
    // its own await, not synchronously during this render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function handleDelete(id: number) {
    if (!confirm("Remove this alert?")) return;
    await deleteAlert(id);
    load();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Alerts</h1>
      <p className="text-sm text-gray-500">Alerts are checked in-app when you open this page. Informational only — no trades are ever placed automatically.</p>

      <AlertForm onCreated={load} />

      {alerts === null && !error && <LoadingState label="Checking alerts…" />}
      {error && <ErrorState message={error} onRetry={load} />}
      {alerts !== null && alerts.length === 0 && <EmptyState title="No alerts set up yet." hint="Add one above for a ticker in your watchlist or positions." />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {alerts?.map((status) => (
          <AlertCard key={status.rule.id} status={status} onDelete={() => handleDelete(status.rule.id)} />
        ))}
      </div>
    </div>
  );
}
