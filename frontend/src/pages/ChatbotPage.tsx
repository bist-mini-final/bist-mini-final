import { Bot } from 'lucide-react';
import { PlannedFeaturePage } from '../shared/PlannedFeaturePage';

export function ChatbotPage() {
  return (
    <PlannedFeaturePage
      title="AI 금융 챗봇"
      description="자연어로 질문하고 실시간 재무 데이터 기반의 정확한 인사이트와 답변을 제공받는 대화형 인터페이스입니다."
      ownerFile="src/pages/ChatbotPage.tsx"
      icon={Bot}
    />
  );
}
