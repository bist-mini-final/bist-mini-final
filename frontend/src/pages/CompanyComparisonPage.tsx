import { Scale } from 'lucide-react';
import { PlannedFeaturePage } from '../shared/PlannedFeaturePage';

export function CompanyComparisonPage() {
  return (
    <PlannedFeaturePage
      title="기업 비교 대시보드"
      description="IBM, Bistelligence, DH Innovation 등 다중 기업 간의 재무 비율, 실적 성장률 및 밸류에이션 지표를 비교 분석하는 공간입니다."
      ownerFile="src/pages/CompanyComparisonPage.tsx"
      icon={Scale}
    />
  );
}
