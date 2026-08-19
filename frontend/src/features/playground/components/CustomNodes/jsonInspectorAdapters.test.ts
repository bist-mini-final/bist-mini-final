import { describe, expect, it } from 'vitest';
import { adaptJsonInspectorContent } from './jsonInspectorAdapters';

describe('adaptJsonInspectorContent', () => {
  it('renders a direct Answer Refiner DTO as markdown', () => {
    const content = adaptJsonInspectorContent('answer_refiner', {
      query_context: { question_id: 'Q1' },
      initial_answer: '초기 답변',
      refined_answer: '**개선 답변** [IS Cell O17]',
      refinement_summary: '셀 검증 완료',
    });

    expect(content).toEqual({
      kind: 'markdown',
      label: 'Refiner 개선 답변',
      markdown: '**개선 답변** [IS Cell O17]',
      truncated: false,
    });
  });

  it('unwraps refined_answer_json without relying on upstream metadata', () => {
    const content = adaptJsonInspectorContent(undefined, {
      refined_answer_json: {
        refined_answer: '최종 답변',
      },
    });

    expect(content.kind).toBe('markdown');
    expect(content).toMatchObject({
      label: 'Refiner 개선 답변',
      markdown: '최종 답변',
      truncated: false,
    });
  });

  it('uses the compact run-history preview for a refined answer', () => {
    const content = adaptJsonInspectorContent('answer_refiner', {
      refined_answer: {
        preview: '축약된 개선 답변',
        characters: 9876,
      },
    });

    expect(content).toEqual({
      kind: 'markdown',
      label: 'Refiner 개선 답변',
      markdown: '축약된 개선 답변',
      sourceCharacters: 9876,
      truncated: true,
    });
  });
});
