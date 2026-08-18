import { Braces, CircleDashed, GitBranch, type LucideIcon } from 'lucide-react';

interface PlannedFeaturePageProps {
  title: string;
  description: string;
  ownerFile: string;
  icon: LucideIcon;
}

/** Stable placeholder that gives each future team feature an independent page boundary. */
export function PlannedFeaturePage({
  title,
  description,
  ownerFile,
  icon: Icon,
}: PlannedFeaturePageProps) {
  return (
    <div className="planned-page">
      <header className="planned-page__header">
        <span className="planned-page__icon">
          <Icon size={22} strokeWidth={1.8} />
        </span>
        <div>
          <span className="planned-page__eyebrow">PLANNED FEATURE</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
      </header>

      <section className="planned-workspace" aria-label={`${title} 구현 준비 영역`}>
        <CircleDashed size={32} strokeWidth={1.5} aria-hidden="true" />
        <h2>팀 기능을 연결할 준비가 되어 있습니다</h2>
        <p>
          공통 내비게이션이나 플레이그라운드를 수정하지 않고 이 페이지 안에서
          독립적으로 구현할 수 있습니다.
        </p>
        <div className="planned-workspace__meta">
          <span><Braces size={15} />{ownerFile}</span>
          <span><GitBranch size={15} />독립 페이지 경계</span>
        </div>
      </section>
    </div>
  );
}
