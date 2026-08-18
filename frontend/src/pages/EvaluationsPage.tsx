import { ChartNoAxesCombined } from 'lucide-react';
import { PlannedFeaturePage } from '../shared/PlannedFeaturePage';

export function EvaluationsPage() {
  return (
    <PlannedFeaturePage
      title="평가"
      description="실험별 정확도, 지연 시간과 비용을 비교하는 공간입니다."
      ownerFile="src/pages/EvaluationsPage.tsx"
      icon={ChartNoAxesCombined}
    />
  );
}
