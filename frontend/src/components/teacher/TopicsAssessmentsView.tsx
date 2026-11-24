import React, { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Assessment, LearningTopic, Question, QuestionType } from '../../types';

export const TopicsAssessmentsView: React.FC = () => {
  const [topics, setTopics] = useState<LearningTopic[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessment, setSelectedAssessment] = useState<Assessment | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // New Topic Form
  const [showTopicForm, setShowTopicForm] = useState(false);
  const [topicName, setTopicName] = useState('');
  const [topicDescription, setTopicDescription] = useState('');

  // New Assessment Form
  const [showAssessmentForm, setShowAssessmentForm] = useState(false);
  const [assessmentTitle, setAssessmentTitle] = useState('');
  const [assessmentDescription, setAssessmentDescription] = useState('');

  // New Question Form
  const [showQuestionForm, setShowQuestionForm] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [questionType, setQuestionType] = useState<QuestionType>('short_answer');
  const [marks, setMarks] = useState<number>(5.0);
  const [expectedAnswer, setExpectedAnswer] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState<number | ''>('');

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [topicsRes, assessmentsRes] = await Promise.all([
        api.getTopics(),
        api.getAssessments(),
      ]);
      setTopics(topicsRes.items);
      setAssessments(assessmentsRes.items);
      if (assessmentsRes.items.length > 0 && !selectedAssessment) {
        handleSelectAssessment(assessmentsRes.items[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load topics and assessments.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSelectAssessment = async (assessment: Assessment) => {
    setSelectedAssessment(assessment);
    try {
      const res = await api.getQuestions(assessment.id);
      setQuestions(res.items);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch questions for assessment.');
    }
  };

  const handleCreateTopic = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      await api.createTopic(topicName, topicDescription || undefined);
      setTopicName('');
      setTopicDescription('');
      setShowTopicForm(false);
      setSuccess('Topic created successfully.');
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to create topic.');
    }
  };

  const handleCreateAssessment = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      const created = await api.createAssessment(assessmentTitle, assessmentDescription || undefined);
      setAssessmentTitle('');
      setAssessmentDescription('');
      setShowAssessmentForm(false);
      setSuccess('Assessment created successfully.');
      loadData();
      handleSelectAssessment(created);
    } catch (err: any) {
      setError(err.message || 'Failed to create assessment.');
    }
  };

  const handleCreateQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAssessment || !selectedTopicId) {
      setError('Please select an assessment and topic.');
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await api.createQuestion(selectedAssessment.id, {
        topic_id: Number(selectedTopicId),
        prompt,
        question_type: questionType,
        marks,
        expected_answer: expectedAnswer,
      });
      setPrompt('');
      setExpectedAnswer('');
      setShowQuestionForm(false);
      setSuccess('Question added to assessment.');
      handleSelectAssessment(selectedAssessment);
    } catch (err: any) {
      setError(err.message || 'Failed to create question.');
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Curriculum & Assessment Management</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Configure learning topics, create baseline assessments, and define questions.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="btn btn-secondary" onClick={() => setShowTopicForm(!showTopicForm)}>
            {showTopicForm ? 'Cancel' : '+ New Topic'}
          </button>
          <button className="btn btn-primary" onClick={() => setShowAssessmentForm(!showAssessmentForm)}>
            {showAssessmentForm ? 'Cancel' : '+ New Assessment'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* New Topic Modal/Box */}
      {showTopicForm && (
        <div className="card" style={{ borderColor: 'var(--primary)' }}>
          <h3 className="card-title" style={{ marginBottom: '12px' }}>Create Learning Topic</h3>
          <form onSubmit={handleCreateTopic}>
            <div className="grid-2">
              <div className="form-group">
                <label className="form-label">Topic Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., Single-Variable Calculus"
                  value={topicName}
                  onChange={(e) => setTopicName(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., Fundamental theorem of calculus and limits"
                  value={topicDescription}
                  onChange={(e) => setTopicDescription(e.target.value)}
                />
              </div>
            </div>
            <button type="submit" className="btn btn-primary btn-sm">Save Topic</button>
          </form>
        </div>
      )}

      {/* New Assessment Modal/Box */}
      {showAssessmentForm && (
        <div className="card" style={{ borderColor: 'var(--primary)' }}>
          <h3 className="card-title" style={{ marginBottom: '12px' }}>Create Assessment</h3>
          <form onSubmit={handleCreateAssessment}>
            <div className="grid-2">
              <div className="form-group">
                <label className="form-label">Assessment Title</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., Midterm Exam: Calculus 101"
                  value={assessmentTitle}
                  onChange={(e) => setAssessmentTitle(e.target.value)}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description (Optional)</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g., In-class written diagnostic test"
                  value={assessmentDescription}
                  onChange={(e) => setAssessmentDescription(e.target.value)}
                />
              </div>
            </div>
            <button type="submit" className="btn btn-primary btn-sm">Save Assessment</button>
          </form>
        </div>
      )}

      {loading && !topics.length ? (
        <div className="loading-container">
          <span className="spinner" />
          <p>Loading curriculum data...</p>
        </div>
      ) : (
        <div className="grid-2" style={{ alignItems: 'flex-start' }}>
          {/* Assessments Column */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Assessments ({assessments.length})</h3>
            </div>
            {assessments.length === 0 ? (
              <div className="empty-state">No assessments yet. Create one above to begin.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {assessments.map((a) => (
                  <div
                    key={a.id}
                    onClick={() => handleSelectAssessment(a)}
                    style={{
                      padding: '12px 16px',
                      borderRadius: 'var(--radius-sm)',
                      background: selectedAssessment?.id === a.id ? 'var(--primary-light)' : 'var(--bg-primary)',
                      border: `1px solid ${selectedAssessment?.id === a.id ? 'var(--primary)' : 'var(--border-color)'}`,
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>{a.title}</div>
                      {a.description && (
                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{a.description}</div>
                      )}
                    </div>
                    <span className="badge badge-neutral">ID #{a.id}</span>
                  </div>
                ))}
              </div>
            )}

            <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border-color)' }}>
              <div style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '8px' }}>
                Configured Topics ({topics.length}):
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {topics.map((t) => (
                  <span key={t.id} className="badge badge-neutral">
                    {t.name}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Questions Column */}
          <div className="card">
            <div className="card-header">
              <div>
                <h3 className="card-title">
                  {selectedAssessment ? `Questions for "${selectedAssessment.title}"` : 'Select an Assessment'}
                </h3>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  {questions.length} question{questions.length !== 1 ? 's' : ''} defined
                </div>
              </div>
              {selectedAssessment && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setShowQuestionForm(!showQuestionForm)}
                >
                  {showQuestionForm ? 'Cancel' : '+ Add Question'}
                </button>
              )}
            </div>

            {showQuestionForm && selectedAssessment && (
              <form
                onSubmit={handleCreateQuestion}
                style={{
                  background: 'var(--bg-primary)',
                  padding: '16px',
                  borderRadius: 'var(--radius-sm)',
                  marginBottom: '16px',
                  border: '1px solid var(--border-color)',
                }}
              >
                <div className="form-group">
                  <label className="form-label">Question Prompt</label>
                  <textarea
                    className="form-textarea"
                    placeholder="e.g., Integrate 3x^2 dx from 0 to 2."
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    required
                  />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Question Type</label>
                    <select
                      className="form-select"
                      value={questionType}
                      onChange={(e) => setQuestionType(e.target.value as QuestionType)}
                    >
                      <option value="short_answer">Short Answer</option>
                      <option value="mcq">Multiple Choice</option>
                      <option value="explain_reasoning">Explain Reasoning</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Marks</label>
                    <input
                      type="number"
                      step="0.5"
                      min="0.5"
                      className="form-input"
                      value={marks}
                      onChange={(e) => setMarks(Number(e.target.value))}
                      required
                    />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Expected Answer / Teacher Key</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="e.g., 8"
                      value={expectedAnswer}
                      onChange={(e) => setExpectedAnswer(e.target.value)}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Learning Topic</label>
                    <select
                      className="form-select"
                      value={selectedTopicId}
                      onChange={(e) => setSelectedTopicId(Number(e.target.value))}
                      required
                    >
                      <option value="">-- Select Topic --</option>
                      {topics.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <button type="submit" className="btn btn-primary btn-sm">
                  Save Question
                </button>
              </form>
            )}

            {!selectedAssessment ? (
              <div className="empty-state">Select an assessment to view and manage questions.</div>
            ) : questions.length === 0 ? (
              <div className="empty-state">No questions defined for this assessment yet.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {questions.map((q, idx) => (
                  <div
                    key={q.id}
                    style={{
                      background: 'var(--bg-primary)',
                      padding: '12px 16px',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-color)',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontWeight: 600 }}>Q{idx + 1}: {q.prompt}</span>
                      <span className="badge badge-info">{q.marks} Marks</span>
                    </div>
                    <div style={{ display: 'flex', gap: '12px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      <span>Type: <strong>{q.question_type}</strong></span>
                      <span>Expected: <code>{q.expected_answer}</code></span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
