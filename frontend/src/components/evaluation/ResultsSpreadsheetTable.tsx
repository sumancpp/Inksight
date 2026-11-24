import React from 'react';
import { EvaluationFinding, InferredQAItem, SubmissionEvaluationSummary } from '../../types';

export interface ResultsSpreadsheetTableProps {
  evaluationSummary?: SubmissionEvaluationSummary | null;
  inferredItems?: InferredQAItem[];
}

interface SpreadsheetRow {
  questionNo: string;
  topic: string;
  studentAnswer: string;
  verdict: string;
  marks: string;
  misconception: string;
}

const getVerdictBadgeStyle = (verdict: string): React.CSSProperties => {
  const v = verdict.toLowerCase();
  if (v.includes('correct') && !v.includes('in') && !v.includes('partial')) {
    return { background: '#ecfdf5', color: '#065f46', border: '1px solid #a7f3d0' };
  }
  if (v.includes('partial')) {
    return { background: '#fffbeb', color: '#92400e', border: '1px solid #fde68a' };
  }
  if (v.includes('incorrect') || v.includes('wrong')) {
    return { background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca' };
  }
  return { background: '#f8fafc', color: '#475569', border: '1px solid #e2e8f0' };
};

export const ResultsSpreadsheetTable: React.FC<ResultsSpreadsheetTableProps> = ({
  evaluationSummary,
  inferredItems,
}) => {
  const rows: SpreadsheetRow[] = [];

  if (evaluationSummary?.runs && evaluationSummary.runs.length > 0) {
    evaluationSummary.runs.forEach((run, runIdx) => {
      const findings: EvaluationFinding[] = run.findings || [];
      findings.forEach((f, fIdx) => {
        const miscText =
          f.misconceptions && f.misconceptions.length > 0
            ? f.misconceptions.map((m) => m.hypothesis || m.linked_concept).filter(Boolean).join('; ')
            : f.misconception_hypothesis || 'None detected';

        const marksText =
          f.marks_awarded !== undefined && f.marks_awarded !== null
            ? `${f.marks_awarded} / ${f.max_marks ?? 1}`
            : 'N/A';

        rows.push({
          questionNo: `Q${runIdx + 1}${findings.length > 1 ? `.${fIdx + 1}` : ''}`,
          topic: f.concept_name || f.remediation_concept || 'General',
          studentAnswer: f.evidence_excerpt || 'See script',
          verdict: (f.verdict || f.category || 'Reviewed').replace(/_/g, ' '),
          marks: marksText,
          misconception: miscText,
        });
      });
    });
  } else if (inferredItems && inferredItems.length > 0) {
    inferredItems.forEach((item, idx) => {
      const miscText =
        item.misconceptions && item.misconceptions.length > 0
          ? item.misconceptions
              .map((m) => m.hypothesis || m.description || m.linked_concept)
              .filter(Boolean)
              .join('; ')
          : 'None detected';
      rows.push({
        questionNo: item.question_number ? `Q${item.question_number}` : `Q${idx + 1}`,
        topic: item.concept_name || 'Inferred Topic',
        studentAnswer: item.student_answer || 'N/A',
        verdict: (item.verdict || 'Evaluated').replace(/_/g, ' '),
        marks:
          item.marks_awarded !== undefined && item.marks_awarded !== null
            ? `${item.marks_awarded} / ${item.max_marks ?? 1}`
            : 'N/A',
        misconception: miscText,
      });
    });
  }

  if (rows.length === 0) {
    return null;
  }

  return (
    <div
      className="excel-results-wrapper"
      data-testid="excel-results-table"
      style={{
        marginTop: '16px',
        marginBottom: '20px',
        background: '#ffffff',
        border: '1px solid #cbd5e1',
        borderRadius: '10px',
        overflow: 'hidden',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div
        style={{
          padding: '10px 14px',
          background: '#f1f5f9',
          borderBottom: '1px solid #cbd5e1',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>📊</span>
          <span>Diagnostic Results Sheet ({rows.length} {rows.length === 1 ? 'Item' : 'Items'})</span>
        </div>
        <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
          Swipe horizontally on mobile to view all columns →
        </span>
      </div>

      <div
        className="excel-table-scroll"
        style={{
          overflowX: 'auto',
          WebkitOverflowScrolling: 'touch',
          width: '100%',
        }}
      >
        <table
          className="excel-table"
          style={{
            width: '100%',
            minWidth: '680px',
            borderCollapse: 'collapse',
            fontSize: '0.84rem',
          }}
        >
          <thead>
            <tr style={{ background: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
              <th style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>Question No</th>
              <th style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>Topic</th>
              <th style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', minWidth: '180px' }}>Student Answer</th>
              <th style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>Verdict</th>
              <th style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>Marks</th>
              <th style={{ padding: '10px 12px', minWidth: '200px' }}>Misconception</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={idx}
                style={{
                  background: idx % 2 === 0 ? '#ffffff' : '#f8fafc',
                  borderBottom: '1px solid #e2e8f0',
                }}
              >
                <td style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap' }}>
                  {row.questionNo}
                </td>
                <td style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', color: '#334155', fontWeight: 500 }}>
                  {row.topic}
                </td>
                <td style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', color: '#1e293b', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
                  {row.studentAnswer}
                </td>
                <td style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', whiteSpace: 'nowrap' }}>
                  <span
                    style={{
                      ...getVerdictBadgeStyle(row.verdict),
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      textTransform: 'capitalize',
                    }}
                  >
                    {row.verdict}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', borderRight: '1px solid #e2e8f0', fontWeight: 700, color: '#0284c7', whiteSpace: 'nowrap' }}>
                  {row.marks}
                </td>
                <td style={{ padding: '10px 12px', color: '#475569', overflowWrap: 'break-word', wordBreak: 'break-word' }}>
                  {row.misconception}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
