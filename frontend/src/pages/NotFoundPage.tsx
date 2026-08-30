import { ArrowLeft, FileQuestion } from 'lucide-react';
import { AppLink } from '../app/router';

export function NotFoundPage() {
  return (
    <div className="not-found-page">
      <FileQuestion size={34} strokeWidth={1.5} />
      <span>404</span>
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>주소를 확인하거나 서비스 홈에서 다시 시작하세요.</p>
      <AppLink to="/" className="ui-button ui-button--secondary ui-button--md">
        <ArrowLeft size={16} /> 홈으로 돌아가기
      </AppLink>
    </div>
  );
}
