import { useEffect, useState } from 'react';
import { BiCardChart } from '../bi/components/charts/BiCardChart';
import { fetchBiDashboard } from '../bi/services/api';
import type { BiCardId, BiDashboardSnapshot } from '../bi/types';
import '../bi/bi.css';
import '../bi/bi-reference.css';

interface ChatVisualizationProps {
  readonly visualization: {
    readonly company_id: string;
    readonly card_id: BiCardId;
  };
}

/** BI chart renderer loaded only for messages that include visualization metadata. */
export function ChatVisualization({ visualization }: ChatVisualizationProps) {
  const [dashboard, setDashboard] = useState<BiDashboardSnapshot | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchBiDashboard(visualization.company_id, controller.signal)
      .then((result) => {
        if (result.kind === 'snapshot') setDashboard(result.dashboard);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [visualization.company_id]);

  if (!dashboard) return null;

  return (
    <div className="chatbot-visualization bi-card" data-card-id={visualization.card_id}>
      <BiCardChart
        cardId={visualization.card_id}
        dashboard={dashboard}
        range="최근 5개"
        size="M"
      />
    </div>
  );
}
