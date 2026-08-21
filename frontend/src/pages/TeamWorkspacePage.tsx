import { Users } from 'lucide-react';
import { PlannedFeaturePage } from '../shared/PlannedFeaturePage';

export function TeamWorkspacePage() {
  return (
    <PlannedFeaturePage
      title="팀 워크스페이스"
      description="팀의 실험, 템플릿과 변경 이력을 공유하는 협업 공간입니다."
      ownerFile="src/pages/TeamWorkspacePage.tsx"
      icon={Users}
    />
  );
}
