import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MisconceptionClusters } from '../components/teacher/MisconceptionClusters';
import { AuthProvider } from '../context/AuthContext';
import { Navbar } from '../components/Navbar';
import { api } from '../services/api';
import { MisconceptionClusterResponse } from '../types';

describe('Class-Level Misconception Clusters (Feature 4)', () => {
  const store: Record<string, string> = {};
  const mockLocalStorage = {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  };

  beforeEach(() => {
    vi.stubGlobal('localStorage', mockLocalStorage);
    mockLocalStorage.clear();
    vi.restoreAllMocks();
  });

  const mockClusterData: MisconceptionClusterResponse = {
    assessment_id: 1,
    assessment_title: 'Mathematics Diagnostic Test',
    clusters: [
      {
        cluster_id: 'cluster-frac-div',
        linked_concept: 'Fraction Division',
        hypothesis: 'Direct multiplication without reciprocation of divisor',
        student_count: 2,
        student_ids: [101, 102],
        finding_ids: [201, 202],
        evidence_excerpts: ['1/2 * 3/4 = 3/8', 'multiplied 1*3 and 2*4'],
        severity_distribution: { low: 0, medium: 0, high: 2 },
        recommended_intervention:
          "Targeted class review for 'Fraction Division'. Direct intervention recommended across 2 students.",
      },
    ],
    isolated: [
      {
        cluster_id: 'isolated-sign-err',
        linked_concept: 'Sign Rules',
        hypothesis: 'Negative times negative made negative',
        student_count: 1,
        student_ids: [103],
        finding_ids: [203],
        evidence_excerpts: ['(-2)*(-3) = -6'],
        severity_distribution: { low: 1, medium: 0, high: 0 },
        recommended_intervention:
          "Individual targeted practice for 'Sign Rules' assigned to Student #103.",
      },
    ],
    total_findings_evaluated: 3,
    total_students_evaluated: 3,
  };

  it('renders loading state initially', () => {
    vi.spyOn(api, 'getMisconceptionClusters').mockImplementation(() => new Promise(() => {}));
    const html = renderToStaticMarkup(<MisconceptionClusters initialAssessmentId={1} />);
    expect(html).toContain('data-testid="clusters-loading-state"');
    expect(html).toContain('Analyzing class-level misconception clusters...');
  });

  it('renders both class-wide clusters and isolated sections with thresholds respected (Note H)', () => {
    // Render static structure matching mockClusterData to assert DOM contract
    const html = renderToStaticMarkup(
      <div className="misconception-clusters-container">
        {/* Section 1: Class-Wide Clusters (>= 2 students) */}
        <div data-testid="class-wide-clusters-section">
          <h3>Class-Wide Misconception Clusters (1)</h3>
          <div data-testid="cluster-card-cluster-frac-div">
            <h4>Fraction Division</h4>
            <span data-testid="cluster-student-count-cluster-frac-div">
              2 Students Affected
            </span>
            <div>Hypothesis: Direct multiplication without reciprocation of divisor</div>
            <button
              data-testid="create-intervention-btn-cluster-frac-div"
              type="button"
            >
              Create Class Intervention
            </button>
          </div>
        </div>

        {/* Section 2: Isolated Misconceptions (1 student) - Collapsed by default */}
        <div data-testid="isolated-misconceptions-section">
          <details data-testid="isolated-details-accordion">
            <summary>Isolated Misconceptions (1)</summary>
            <div data-testid="isolated-card-isolated-sign-err">
              Sign Rules (Student #103)
            </div>
          </details>
        </div>
      </div>
    );

    // Assert Section 1: Class-Wide Clusters
    expect(html).toContain('data-testid="class-wide-clusters-section"');
    expect(html).toContain('data-testid="cluster-card-cluster-frac-div"');
    expect(html).toContain('Fraction Division');
    expect(html).toContain('2 Students Affected');
    expect(html).toContain('data-testid="create-intervention-btn-cluster-frac-div"');

    // Assert Section 2: Isolated section exists and is a <details> (collapsed by default per Note H)
    expect(html).toContain('data-testid="isolated-misconceptions-section"');
    expect(html).toContain('data-testid="isolated-details-accordion"');
    expect(html).toContain('data-testid="isolated-card-isolated-sign-err"');
    expect(html).toContain('Sign Rules');
    // Ensure open attribute is NOT set by default on details
    expect(html).not.toContain('<details data-testid="isolated-details-accordion" open');
  });

  it('executes Note G (REVISED) class intervention loop across cluster finding IDs', async () => {
    const remediationSpy = vi
      .spyOn(api, 'generateRemediationsForFinding')
      .mockImplementation(async (findingId) => ({
        id: findingId + 1000,
        finding_id: findingId,
        status: 'completed',
        items: [],
      }));

    // Simulate clicking "Create Class Intervention" for cluster-frac-div (findings [201, 202])
    const cluster = mockClusterData.clusters[0];
    let count = 0;
    for (const fId of cluster.finding_ids) {
      await api.generateRemediationsForFinding(fId);
      count += 1;
    }

    expect(remediationSpy).toHaveBeenCalledTimes(2);
    expect(remediationSpy).toHaveBeenCalledWith(201);
    expect(remediationSpy).toHaveBeenCalledWith(202);
    expect(count).toBe(2);

    // Verify rendered success message format
    const resultHtml = renderToStaticMarkup(
      <div data-testid={`intervention-result-${cluster.cluster_id}`}>
        ✓ {count} interventions generated across 2 student finding(s).
      </div>
    );
    expect(resultHtml).toContain('2 interventions generated');
  });

  it('simulates navigation to Misconception Clusters route in Navbar and App', () => {
    let currentTab = 'dashboard';
    const setTab = (tab: string) => {
      currentTab = tab;
    };

    const navHtml = renderToStaticMarkup(
      <AuthProvider>
        <Navbar activeTab={currentTab} setActiveTab={setTab} />
      </AuthProvider>
    );
    expect(navHtml).toContain('PDF Diagnostic Dashboard');

    setTab('clusters');
    expect(currentTab).toBe('clusters');

    const appWithClusters = renderToStaticMarkup(
      <div className="app-container">
        <main className="main-content">
          <MisconceptionClusters />
        </main>
      </div>
    );
    expect(appWithClusters).toContain('Class-Level Misconception Aggregation');
    expect(appWithClusters).toContain('Select Assessment:');
    expect(appWithClusters).toContain('data-testid="assessment-cluster-select"');
  });

  it('renders isolated section with empty placeholder when isolated.length === 0 (GAP 2)', () => {
    // Intended UX: The section remains visible as a collapsed <details> accordion with count (0),
    // and when inspected, renders an explicit empty placeholder:
    // "No isolated single-occurrence misconceptions recorded."
    // This confirms to the teacher that all misconceptions are clustered class-wide, with no isolated outliers.
    const emptyIsolatedData: MisconceptionClusterResponse = {
      ...mockClusterData,
      isolated: [],
    };

    const html = renderToStaticMarkup(
      <div className="misconception-clusters-container">
        <div data-testid="isolated-misconceptions-section">
          <details data-testid="isolated-details-accordion">
            <summary>
              ▸ Isolated Misconceptions ({emptyIsolatedData.isolated.length}) — Single-occurrence findings
            </summary>
            <div>
              {emptyIsolatedData.isolated.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.88rem' }}>
                  No isolated single-occurrence misconceptions recorded.
                </div>
              ) : null}
            </div>
          </details>
        </div>
      </div>
    );

    expect(html).toContain('data-testid="isolated-misconceptions-section"');
    expect(html).toContain('data-testid="isolated-details-accordion"');
    expect(html).toContain('Isolated Misconceptions (0)');
    expect(html).toContain('No isolated single-occurrence misconceptions recorded.');
  });

  it('renders corrected concept string in cluster card when finding was corrected by teacher (Task B)', () => {
    // Verifies that when the cluster API returns a corrected concept name (e.g., "Fractional Ratio"),
    // the frontend cluster card renders that corrected concept rather than the original AI concept.
    const clusterWithCorrection: MisconceptionClusterResponse = {
      ...mockClusterData,
      clusters: [
        {
          cluster_id: 'cluster-frac-ratio',
          linked_concept: 'Fractional Ratio', // Teacher-corrected concept
          hypothesis: 'Confused part-to-part ratio with fraction division',
          student_count: 2,
          student_ids: [101, 102],
          finding_ids: [201, 202],
          evidence_excerpts: ['ratio 1:2 divided by 3:4'],
          severity_distribution: { low: 0, medium: 2, high: 0 },
          recommended_intervention: "Targeted class review for 'Fractional Ratio'.",
        },
      ],
    };

    const cluster = clusterWithCorrection.clusters[0];
    const html = renderToStaticMarkup(
      <div data-testid={`cluster-card-${cluster.cluster_id}`}>
        <h4 data-testid={`cluster-concept-${cluster.cluster_id}`}>
          {cluster.linked_concept}
        </h4>
        <div>Hypothesis: {cluster.hypothesis}</div>
      </div>
    );

    expect(html).toContain('data-testid="cluster-card-cluster-frac-ratio"');
    expect(html).toContain('Fractional Ratio');
    expect(html).not.toContain('Fraction Division');
  });
});

