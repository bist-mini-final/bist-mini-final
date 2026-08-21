import { Database } from 'lucide-react';
import { PlannedFeaturePage } from '../shared/PlannedFeaturePage';

export function DataSourcesPage() {
  return (
    <PlannedFeaturePage
      title="데이터 소스"
      description="업로드한 문서, 스프레드시트와 인덱스 자산을 관리하는 공간입니다."
      ownerFile="src/pages/DataSourcesPage.tsx"
      icon={Database}
    />
  );
}
