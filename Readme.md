# NetHealth AI - Intelligent Network Observability Platform

## 1. Problem Statement

### Context & Background
Smart factories operate on converged industrial networks where Operational Technology (OT) devices (PLCs, sensors, drives) and IT systems share a unified infrastructure. These networks span all layers from L1 (Physical) to L7 (Application). A failure in any layer—damaged cables, switch congestion, or protocol errors—can disrupt production.

### Current Challenges
- **Ambiguity**: L1 issues (e.g., CRC errors) often masquerade as L3 routing issues, misleading operators.
- **Siloed Visibility**: OT protocols (Profinet, Modbus) and IT traffic are often monitored by separate tools.
- **Complexity**: Diagnosing cross-layer problems in real-time is difficult without expert knowledge.
- **Asset Sprawl**: Managing thousands of devices without a unified topological view.

### Objectives
To design an AI-assisted tool that provides:
- **L1-L7 Visibility**: Monitoring KPIs across all network layers.
- **Asset Visualization**: Topology-aware mapping of network devices.
- **AI-Driven Diagnostics**: Automated root cause analysis.
- **Unified Dashboard**: A single pane of glass for operators.

---

## 2. Technology Stack

We selected a stack optimized for **rapid prototyping**, **data integrity**, and **explainable AI**.

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Language** | **Python 3.9+** | Core application logic and data processing. |
| **Database** | **TimescaleDB** (PostgreSQL) | Unified storage for time-series metrics and relational asset data. |
| **Backend** | **SQLAlchemy / Pydantic** | ORM and data validation layer. |
| **Frontend** | **Streamlit** | Interactive operator dashboard and visualization. |
| **AI / ML** | **scikit-learn** (Isolation Forest) | Unsupervised anomaly detection. |
| **Probabilistic AI** | **pgmpy** (Bayesian Networks) | **Key Differentiator**: Explainable root cause diagnosis. |
| **Causality** | **statsmodels** (Granger Causality) | Statistical validation of metric relationships. |
| **Data Collection** | **pysnmp**, **pymodbus** | Industrial protocol integration. |

---

## 3. Why This Stack? (Design Rationale)

### 1. TimescaleDB (PostgreSQL)
We chose TimescaleDB over purely Time-Series Databases (TSDBs) like InfluxDB because industrial networks require **Relational Context**.
- **Requirement**: Correlating a metric spike (Time-Series) with the device's location in the topology (Relational).
- **Benefit**: Standard SQL allows complex joins between `metrics` and `assets`, simplifying the "Asset Monitoring" requirement.

### 2. Bayesian Networks (pgmpy)
We chose Probabilistic Graphical Models over Deep Learning (Neural Networks).
- **Requirement**: Operators must trust the AI. A "Black Box" prediction is insufficient for critical infrastructure.
- **Benefit**: Bayesian Networks provide **Explainability**. The system can show *why* it reached a conclusion (e.g., "High Probability of Cable Failure due to correlated SNR drop and CRC errors") and quantify **Uncertainty**.

### 3. Streamlit
We chose Streamlit over React/Vue.js.
- **Requirement**: Rapid iteration on data visualizations.
- **Benefit**: Allowed us to focus 90% of effort on the Data and AI capabilities rather than frontend boilerplate, enabling a rich, interactive "Operator Dashboard" in minimal time.

### Alternatives Considered & Advantages

| Alternative | Trade-off | Why We Chose Current Stack |
| :--- | :--- | :--- |
| **InfluxDB** | Optimized for write speed, but weak relational data support. | **TimescaleDB Advantage**: Ability to join metrics with asset inventory in a single query is critical for topology-aware diagnostics. |
| **Deep Learning (LSTM/CNN)** | High accuracy for patterns, but minimal explainability. | **Bayesian Network Advantage**: Transparent reasoning paths. operators need to know *why* to take action (e.g., replace cable vs. reboot switch). |
| **Elasticsearch (ELK)** | Great for logs, complex for time-series math. | **Python/Pandas Advantage**: Superior ecosystem for the complex mathematical modeling required for Thermal Physics and Granger Causality. |

---

## 4. Approach to the Problem

Our solution architecture follows a **Data-to-Insight Pipeline**:

### Phase 1: Unified Data Modeling (L1-L7)
We designed a schema that normalizes diverse signals into a common structure:
- **L1 (Physical)**: Signal-to-Noise Ratio (SNR), Bit Error Rate (BER), Temperature.
- **L3 (Network)**: Packet Loss, Latency, TTL.
- **L7 (Application)**: Response Time, Transaction Success Rate.

### Phase 2: Dual-Mode Ingestion
To satisfy both "Simulation Allowed" and "Real Relevance" constraints:
- **Synthetic Mode**: A physics-based generator simulates faults (Cable Break, EMI, Congestion) to train and validate the AI.
- **Production Mode**: Async `asyncio` collectors ingest live SNMP v3 and Modbus TCP data, ready for factory deployment.

### Phase 3: The Intelligence Layer
We implemented a multi-stage AI pipeline:
1.  **Detect**: Isolation Forest identifies *when* behavior deviates from normal (Anomaly Detection).
2.  **Diagnose**: Bayesian Networks correlate symptoms across layers (e.g., L1 errors causing L4 retransmits) to find the *Root Cause*.
3.  **Verify**: Granger Causality tests run on historical data to statistically *prove* the directional influence between metrics.

### Phase 4: Operator Dashboard
Designed a "Command Center" interface:
- **Map View**: Visual topology with color-coded health status.
- **Thermal Twin**: Physics-based view of cable/device temperature stress.
- **AI Insights**: Natural language explanations of diagnosed issues.

---

## 5. Difficulties Faced

### 1. The "Cross-Layer Masquerade"
*Challenge*: A physical cable fault (L1) often manifests primarily as Application Latency (L7) due to TCP retransmissions, hiding the root cause.
*Solution*: We implemented **Topology-Aware Correlation**. The system uses the network graph to trace symptoms upstream, identifying that the L7 latency is merely a symptom of the downstream L1 cable issue.

### 2. Simulating Industrial Physics
*Challenge*: Generating realistic "bad data" for AI validation is difficult. Random noise doesn't look like a real thermal failure.
*Solution*: We implemented a **Thermal Physics Simulator** using Joule's Law ($P=I^2R$). This models how increased traffic load heats up cables, increasing resistance and degrading signals, creating realistic, physics-compliant failure signatures.

### 3. Proof vs. Prediction
*Challenge*: AI models can find false correlations.
*Solution*: We integrated **Granger Causality Testing**. Before asserting a relationship (e.g., "High Temp causes Latency"), the system performs statistical hypothesis testing (p-value < 0.05) to confirm causality, reducing false alarms.

---

## 6. Results & Outcomes

### Quantitative Performance
- **Diagnostic Accuracy**: **75.0%** (Validated on 100 diverse fault scenarios).
- **Detection Precision**: **75.4%**, minimizing false positives in critical industrial environments.
- **Speed**: Sub-second diagnosis latency for real-time monitoring.

### Key Deliverables
- **Production-Ready Prototype**: Functional end-to-end system with live data ingestion.
- **Validated AI**: Proven ability to distinguish between EMI, Cable Failure, and Congestion.
- **Comprehensive Dashboard**: Tabbed interface serving Operators (Health Map), Engineers (Thermal Twin), and Managers (System Performance).

### Conclusion
NetHealth AI successfully bridges the gap between IT and OT observability. By leveraging **Explainable AI** and **Physics-Based Modeling**, it provides the deep visibility and trusted insights required to maintain uptime in modern smart factories.
