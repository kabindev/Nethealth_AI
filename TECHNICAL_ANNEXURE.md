# Technical Annexure — NetHealth AI
## Intelligent Network Observability Platform

**Version:** 1.0  
**Date:** February 2026  
**Project Category:** Track 1 — Industrial Network Intelligence  

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Data Schema & Models](#2-data-schema--models)
3. [Data Ingestion Pipeline](#3-data-ingestion-pipeline)
4. [KPI Engine — OSI Layer Health Scoring](#4-kpi-engine--osi-layer-health-scoring)
5. [Anomaly Detection — Isolation Forest](#5-anomaly-detection--isolation-forest)
6. [Bayesian Diagnostic Engine](#6-bayesian-diagnostic-engine)
7. [Granger Causality Engine](#7-granger-causality-engine)
8. [Thermal Network Digital Twin Simulator](#8-thermal-network-digital-twin-simulator)
9. [Deep Learning Components](#9-deep-learning-components)
10. [Security Monitoring Subsystem](#10-security-monitoring-subsystem)
11. [Dashboard Architecture](#11-dashboard-architecture)
12. [Database Design](#12-database-design)
13. [Configuration & Deployment](#13-configuration--deployment)
14. [Performance Benchmarks & Validation](#14-performance-benchmarks--validation)
15. [Dependency Reference](#15-dependency-reference)

---

## 1. System Architecture Overview

NetHealth AI follows a **layered, modular pipeline** architecture. Data flows from raw network signals through a multi-stage AI processing chain into a unified operator dashboard.

```
┌──────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION LAYER                      │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐│
│  │ Synthetic CSV│  │  SNMP / Mod  │  │  Live Network Collector  ││
│  │  Generator   │  │  bus Collect │  │  (Ping + TCP Probe)      ││
│  └──────┬───────┘  └──────┬───────┘  └───────────┬─────────────┘│
└─────────┼──────────────────┼────────────────────────┼────────────┘
          └──────────────────┴────────────────────────┘
                             │ Normalised Metric Records
┌──────────────────────────────────────────────────────────────────┐
│                        CORE PROCESSING LAYER                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────┐│
│  │  KPI Engine  │   │  ONE Score Calc  │   │  Topology Builder  ││
│  │ (L1/L3/L4/L7)│   │ (Weighted Aggr.) │   │  (Graph Topology)  ││
│  └──────┬───────┘   └────────┬─────────┘   └────────┬──────────┘│
└─────────┼────────────────────┼────────────────────────┼──────────┘
          └────────────────────┴────────────────────────┘
                             │ KPIs + Health Scores
┌──────────────────────────────────────────────────────────────────┐
│                      INTELLIGENCE LAYER                          │
│  ┌──────────────┐  ┌───────────────────┐  ┌───────────────────┐ │
│  │  Isolation   │  │  Bayesian Network  │  │  Granger Causality│ │
│  │  Forest      │  │  (Fault Diagnose)  │  │  (Causal Proof)   │ │
│  │  (Detect)    │  └──────────┬────────┘  └────────┬──────────┘ │
│  └──────┬───────┘             │                    │            │
│  ┌──────┴───────┐  ┌──────────┴────────┐  ┌────────┴──────────┐ │
│  │  Thermal     │  │  GNN Correlator   │  │  LSTM Forecaster  │ │
│  │  Simulator   │  │  (Deep Learning)  │  │  (Time-Series)    │ │
│  └──────────────┘  └───────────────────┘  └───────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                             │ Diagnosis + Predictions
┌──────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                          │
│         Streamlit Dashboard (5–6 Tabs + AI Chat)                 │
│   Network Map │ Floor Plan │ Thermal Twin │ AI Insights │ Security│
└──────────────────────────────────────────────────────────────────┘
```

### Source Package Structure

| Package | Path | Responsibility |
|---|---|---|
| `core` | `src/core/` | Data models, KPI engine, topology |
| `ingestion` | `src/ingestion/` | SNMP, Modbus, live collectors |
| `intelligence` | `src/intelligence/` | All AI/ML components |
| `orchestration` | `src/orchestration/` | Pipeline coordinator |
| `dashboard` | `src/dashboard/` | Streamlit app + components |
| `database` | `src/database/` | TimescaleDB ORM layer |
| `security` | `src/security/` | Rogue detection + config drift |
| `utils` | `src/utils/` | Shared utilities, live data bridge |

---

## 2. Data Schema & Models

### 2.1 Network Metric Record

Every data point collected — synthetic, SNMP, or live — is normalised into the following schema before entering the processing pipeline:

| Field | Type | Description |
|---|---|---|
| `timestamp` | `datetime` | UTC timestamp of measurement |
| `asset_id` | `str` | Unique device identifier (e.g., `switch-core-01`) |
| `metric_name` | `str` | Metric key (see §2.2) |
| `value` | `float` | Measured value |
| `unit` | `str` | Unit of measure (ms, percent, dB, ratio) |

### 2.2 Supported Metric Keys

| Metric Key | OSI Layer | Unit | Description |
|---|---|---|---|
| `snr_db` | L1 Physical | dB | Signal-to-Noise Ratio |
| `ber` | L1 Physical | ratio | Bit Error Rate |
| `crc_error` | L1 Physical | count | CRC error frames per interval |
| `link_flaps` | L1 Physical | count | Link state changes per interval |
| `rssi` | L1 Physical | dBm | Received Signal Strength |
| `packet_loss` | L3 Network | percent | Packet loss percentage |
| `latency` | L3 Network | ms | Round-trip time |
| `ttl` | L3 Network | hops | Time-to-Live |
| `tcp_retransmits` | L4 Transport | count | TCP retransmission count |
| `jitter` | L4 Transport | ms | Latency variation |
| `response_time` | L7 Application | ms | Application response time |
| `transaction_success_rate` | L7 Application | percent | Successful transactions |

### 2.3 Asset Inventory Schema (`assets.json`)

```json
{
  "asset_id": "switch-core-01",
  "name": "Core Switch A",
  "type": "switch",
  "ip_address": "192.168.1.1",
  "layer": "L3",
  "location": {"x": 120, "y": 80},
  "connections": ["plc-01", "plc-02", "router-01"],
  "cable_gauge": "24AWG",
  "cable_length_m": 50,
  "age_months": 36
}
```

---

## 3. Data Ingestion Pipeline

### 3.1 Synthetic Data Mode

Pre-generated CSV files are loaded for demonstration and validation purposes.

| File | Scenario |
|---|---|
| `data/raw/metrics_timeseries.csv` | Normal network operation |
| `data/raw/metrics_faulty.csv` | Simulated cable failure (L1 fault propagating to L7) |
| `data/raw/metrics_severe.csv` | Severe fault — L4 congestion attack |
| `data/synthetic/metrics_extended.csv` | Extended dataset (~20MB) for model validation |

The physics-based Thermal Simulator (§8) generates the faulty datasets, ensuring realistic failure signatures rather than random noise.

### 3.2 Production Mode (SNMP / Modbus)

| File | Protocol | Target Devices |
|---|---|---|
| `src/ingestion/snmp_collector.py` | SNMP v3 | Managed switches, routers |
| `src/ingestion/modbus_collector.py` | Modbus TCP | PLCs, VFDs, industrial controllers |
| `src/ingestion/profinet_collector.py` | Profinet | Siemens PROFINET devices |

All collectors run asynchronously using Python `asyncio`, polling at configurable intervals (default 30 s for SNMP, 5 s for Modbus).

**SNMP Collected OIDs (examples):**

| OID | Metric |
|---|---|
| `IF-MIB::ifInErrors` | CRC / input error counter |
| `IF-MIB::ifInDiscards` | Packet discard count |
| `IF-MIB::ifInOctets` | Inbound traffic (bytes) |
| `RFC1213-MIB::ipInReceives` | IP packet receive count |

### 3.3 Live Network Mode (Real LAN)

The `LiveNetworkCollector` (`src/ingestion/live_collector.py`) discovers and monitors devices on the operator's local network without requiring SNMP hardware.

**Discovery:** Parallel ping-sweep of subnet using OS `ping` command (`/24` max, 50 concurrent workers via `ThreadPoolExecutor`).

**Per-Device Probing (every `poll_interval` seconds, default 15 s):**

| Probe | Method | Metric Produced |
|---|---|---|
| ICMP Ping | OS `ping` command | `latency` (ms) |
| Multi-ping (n=4) | Sequential pings | `packet_loss` (%) |
| TCP Connect | `socket.create_connection()` | `tcp_<service>_rtt` (ms) |
| SNR Proxy | Derived from latency | `snr_db` (dB) |
| BER Proxy | Derived from packet loss | `ber` (ratio) |
| CRC Proxy | Derived from packet loss | `crc_error` (count) |

**SNR Estimation Formula:**
```
snr_proxy = max(10.0, 40.0 − (latency_ms / 5.0))
```
Maps 1 ms → ~38 dB ; 100 ms → ~20 dB.

**Data Storage:** Thread-safe `RollingMetricStore` (max 200 rows per metric per device). Data bridged to the AI pipeline via `src/utils/live_data_bridge.py`.

---

## 4. KPI Engine — OSI Layer Health Scoring

The KPI Engine (`src/core/kpi_engine/`) computes a per-device health score for each OSI layer and aggregates them into a single **ONE Score** (0–100).

### 4.1 Layer Score Calculations

#### L1 — Physical Layer (`l1_physical.py`)

| Condition | Deduction |
|---|---|
| CRC errors > 100 | −40 points |
| CRC errors > 10 | −20 points |
| CRC errors > 0 | −5 points |
| Link flaps > 10 | −40 points |
| Link flaps > 2 | −20 points |
| RSSI < −85 dBm | −30 points |
| RSSI < −75 dBm | −10 points |

#### L3 — Network Layer (`l3_network.py`)

Based on packet loss and latency thresholds with linear penalty scaling.

#### L4 — Transport Layer (`l4_transport.py`)

Based on TCP retransmit count and jitter measurements.

#### L7 — Application Layer (`l7_application.py`)

Based on application response time and transaction success rate.

### 4.2 ONE Score Aggregation (`one_score.py`)

```
ONE Score = (L1 × 0.30) + (L3 × 0.30) + (L4 × 0.20) + (L7 × 0.20)
```

**Critical Veto Logic:** If any single layer score drops below 50, the final ONE Score is capped at 59 — preventing a failing physical layer from being masked by healthy upper layers.

```python
if min(s1, s3, s4, s7) < 50:
    final_score = min(final_score, 59.0)
```

### 4.3 Health Status Thresholds

| ONE Score Range | Status | Colour |
|---|---|---|
| 80 – 100 | Healthy | 🟢 Green |
| 60 – 79 | Degraded | 🟡 Yellow |
| 40 – 59 | Warning | 🟠 Orange |
| 0 – 39 | Critical | 🔴 Red |

---

## 5. Anomaly Detection — Isolation Forest

**Module:** `src/intelligence/anomaly_detector.py`  
**Algorithm:** scikit-learn `IsolationForest`

### 5.1 Principle

Isolation Forest detects anomalies by randomly partitioning the feature space. Points that are isolated with fewer splits (shorter path length in the tree) are flagged as anomalies — they are statistically unusual.

### 5.2 Configuration

| Parameter | Value | Effect |
|---|---|---|
| `contamination` | 0.05 | Expects ~5% of training data to be anomalous |
| `random_state` | 42 | Reproducible results |

### 5.3 Training & Detection Workflow

1. **Train** on historical baseline (`metrics_timeseries.csv`) using all numeric metric features.
2. **Detect**: For each new window, `decision_function()` returns anomaly scores (lower = more anomalous). `predict()` returns −1 (anomaly) or +1 (normal).
3. Output: DataFrame with `anomaly_score` and `is_anomaly` (boolean) columns.

### 5.4 Anomaly Severity Classification

Anomalies are classified by the orchestrator into `low`, `medium`, `high`, or `critical` based on the combination of:
- Which metrics are anomalous
- The magnitude of the deviation
- Layer tracing (L1 fault → manifests as L7 symptom)

---

## 6. Bayesian Diagnostic Engine

**Module:** `src/intelligence/bayesian_diagnostics.py`  
**Library:** `pgmpy` (Probabilistic Graphical Models)

### 6.1 Purpose

Provides **explainable root-cause diagnosis** with a probability distribution over possible fault causes. Unlike black-box models, operators see exactly *why* a cause is suspected and with what confidence.

### 6.2 Bayesian Network Structure

The network encodes domain knowledge as a Directed Acyclic Graph (DAG):

```
CableAge ─────┐
               ├──→ CableFailure ──┐
AmbientTemp ──┤                    ├──→ CRCErrors ──→ PacketLoss ──→ Latency
               └──→ ConnectorOxidation ─┘    ↑
EMI_Source ───────────────────────────────────┘
ConfigError ──────────────────────────────────────────→ PacketLoss
```

### 6.3 Conditional Probability Tables (CPDs)

All CPDs are hand-encoded with domain expertise:

**P(CableFailure | CableAge, AmbientTemp)** — example values:

| Cable Age | Ambient Temp | P(Failure) |
|---|---|---|
| New | Normal | 0.05 |
| Old | High | 0.25 |
| Very Old | Very High | 0.70 |

**P(CRCErrors | CableFailure, ConnectorOxidation, EMI_Source):** 3-state variable (Low / Medium / High CRC count).

### 6.4 Inference & Diagnosis

Uses **Variable Elimination** (`pgmpy.inference.VariableElimination`) to query posterior probabilities given observed evidence:

```python
evidence = {"CRCErrors": "High", "PacketLoss": "Medium"}
result = engine.query(variables=["CableFailure"], evidence=evidence)
# → P(CableFailure=True) = 0.684
```

### 6.5 Confidence Classification

| Primary Cause Probability | Confidence Level |
|---|---|
| > 60% | High |
| 40% – 60% | Medium |
| < 40% | Low |

### 6.6 Online Bayesian Updating

Beliefs can be updated incrementally as new evidence arrives (e.g., from technician inspection):

```
Initial Evidence: {CRCErrors=High}           → P(CableFailure) = 0.62
New Evidence:     {TDR_Result=Pass}           → P(CableFailure) = 0.18 (drops)
                                               → P(EMI_Source)  = 0.55 (rises)
```

### 6.7 Recommended Actions Output

For each plausible cause (probability > 15%), the engine generates a specific action:

| Root Cause | Recommended Action |
|---|---|
| `CableFailure` | Test cable with TDR (Time Domain Reflectometer) |
| `ConnectorOxidation` | Inspect connectors for oxidation/corrosion |
| `EMI_Source` | Scan for EMI sources (motors, VFDs, welders) |
| `ConfigError` | Verify network configuration (VLANs, QoS settings) |

---

## 7. Granger Causality Engine

**Module:** `src/intelligence/causality_engine.py`  
**Library:** `statsmodels`

### 7.1 Purpose

Statistically **proves directional influence** between network metrics. Addresses the risk of spurious correlations in the Bayesian model by requiring statistical evidence (p-value < 0.05) before asserting a causal link.

### 7.2 Granger Causality Principle

Metric A **Granger-causes** Metric B if past values of A significantly improve the prediction of B beyond B's own history alone (F-test on nested VAR models).

### 7.3 Test Workflow

```
1. Pre-process: Augmented Dickey-Fuller (ADF) stationarity test
2. Differencing: First-order differencing if not stationary
3. Lag selection: Test lags 1…max_lag (default 5), select by minimum F-test p-value
4. Decision: p_value < 0.05 → causal edge confirmed
5. Output: CausalEdge(from, to, strength=1-p, lag, p_value)
```

**Minimum data requirement:** 30 time-series points for reliable testing.

### 7.4 CausalGraph Data Structure

Proven edges are stored in a `CausalGraph` object supporting:
- `get_causing_metrics(target)` — find upstream causes
- `get_affected_metrics(source)` — find downstream effects
- `detect_feedback_loops()` — DFS-based cycle detection
- `get_optimal_lag(from, to)` — retrieve time delay of causal effect

### 7.5 Example Proven Causal Chain

```
switch-01.crc_error → switch-01.packet_loss   (lag=1, p=0.003, strength=0.997)
switch-01.packet_loss → plc-02.latency        (lag=2, p=0.018, strength=0.982)
plc-02.latency → server-01.response_time      (lag=3, p=0.042, strength=0.958)
```

This chain proves: a physical CRC error on the switch causes downstream application latency within 3 measurement intervals.

---

## 8. Thermal Network Digital Twin Simulator

**Module:** `src/intelligence/thermal_simulator.py`  
**Physics Basis:** Joule's Law, temperature coefficient of copper resistance, QPSK BER formula

### 8.1 Purpose

Predicts **cable degradation and remaining useful life** using physics-based modelling. Used both to generate realistic fault training data and to display predictive maintenance timelines on the dashboard.

### 8.2 Physics Model — Step-by-Step Calculation

**Step 1: Current from Traffic Load**
```
I_rms = (traffic_mbps / 1000) × 0.35 A/Gbps
```
Capped at maximum rated current per cable gauge (e.g., 0.577 A for 24 AWG).

**Step 2: Temperature Rise (I²R Heating — Joule's Law)**
```
ΔT = I² × R_cable × thermal_resistance
R_cable = (ρ_Cu / cross_section) × length
```
Where `ρ_Cu = 0.0175 Ω·mm²/m` (resistivity of copper).

**Step 3: Temperature-Dependent Resistance**
```
R(T) = R₀ × [1 + α(T − T₀)]
```
Where `α = 0.00393 /°C` is the temperature coefficient of copper.

**Step 4: Aging Factor**
```
aging_factor = 1.0 + (age_months / 120) × 0.15
```
15% degradation over 10 years (120 months), capped at 50%.

**Step 5: SNR Degradation from Resistance**
```
attenuation_dB/m = 0.05 × √(R × f_MHz / 100)
SNR_dB = 40.0 − (attenuation_dB/m × length)
```
Baseline SNR of 40 dB for a healthy cable.

**Step 6: Bit Error Rate from SNR (QPSK approximation)**
```
BER ≈ 0.5 × exp(−SNR_linear / 2)
```
Failure threshold: `BER ≥ 1×10⁻⁹`

**Step 7: Failure Timeline Extrapolation**
```
days_until_failure = (BER_threshold − BER_current) / BER_rate
```
Linear extrapolation over 90-day horizon.

### 8.3 Cable Specifications

| Gauge | Cross-Section (mm²) | Max Current (A) |
|---|---|---|
| 26 AWG | 0.129 | 0.361 |
| 24 AWG | 0.205 | 0.577 |
| 22 AWG | 0.326 | 0.920 |

### 8.4 Maintenance Recommendations

| Condition | Recommended Action |
|---|---|
| `days_until_failure < 30` | URGENT: Schedule replacement immediately |
| `days_until_failure < 90` | Plan replacement in next maintenance window |
| `T_operating > 60°C` | Improve ventilation / reduce traffic load |
| `age_months > 60` | Plan replacement within 6 months |
| Otherwise | No action — continue monitoring |

---

## 9. Deep Learning Components

### 9.1 Graph Neural Network Correlator

**Module:** `src/intelligence/gnn_correlator.py`  
**Framework:** PyTorch + PyTorch Geometric

The GNN models the network as a graph where nodes are devices and edges are physical connections. It performs **fault correlation** across multiple hops in the topology — identifying which devices are most likely the root cause of a distributed fault.

| Attribute | Value |
|---|---|
| Architecture | Graph Convolutional Network (GCN) |
| Node features | 32-dimensional device metric vectors |
| Edge features | 16-dimensional link metric vectors |
| Output | Per-node failure probability (0–1) |
| Training | `src/intelligence/train_gnn.py` |

### 9.2 LSTM Forecaster

**Module:** `src/intelligence/lstm_forecaster.py`  
**Framework:** PyTorch

Used to forecast future metric values (e.g., latency, packet loss) with configurable time horizons.

| Attribute | Value |
|---|---|
| Architecture | LSTM with Attention Mechanism |
| Horizons supported | 1 h, 6 h, 24 h |
| Outputs | Predicted values + confidence intervals + attention weights |
| Training | `src/intelligence/train_lstm.py` |

### 9.3 Mode Selection Logic (Orchestrator)

```python
if use_deep_learning and gnn_model_path:
    correlation_method = 'gnn'       # GNN for fault correlation
else:
    correlation_method = 'granger'   # Granger causality fallback

if use_deep_learning and lstm_model_path:
    forecast_method = 'lstm'         # LSTM for forecasting
else:
    forecast_method = 'arima'        # ARIMA fallback
```

### 9.4 Combined Diagnosis Confidence Weighting

When both Bayesian and GNN results are available:
```
combined_confidence = 0.40 × bayesian_confidence + 0.60 × gnn_confidence
```

---

## 10. Security Monitoring Subsystem

**Modules:** `src/security/rogue_detector.py`, `src/security/config_monitor.py`

### 10.1 Rogue Device Detection (`RogueDeviceDetector`)

Detects unauthorised devices appearing on the network by comparing observed device inventory against a known-good whitelist. Each new MAC address or device not in the whitelist triggers an alert with:

| Field | Description |
|---|---|
| `device_id` | Detected device identifier |
| `mac_address` | Hardware MAC address |
| `reason` | Why it was flagged |
| `severity` | `CRITICAL` or `WARNING` |
| `confidence` | Detection confidence (0–1) |

### 10.2 Configuration Drift Detection (`ConfigurationMonitor`)

Tracks device configuration snapshots and compares them against baseline. Any unauthorised change (VLAN modification, routing change, port security change) raises a drift alert:

| Field | Description |
|---|---|
| `device_id` | Affected device |
| `change_type` | Type of configuration change |
| `severity` | `CRITICAL` / `WARNING` / `INFO` |
| `changes` | Dictionary of changed parameters |

### 10.3 Security Score Calculation

```
security_score = 100 − (critical_alerts × 20) − (warning_alerts × 5)
score = max(0, security_score)
```

---

## 11. Dashboard Architecture

**Framework:** Streamlit  
**Entry Point:** `src/dashboard/app.py`  
**Theme:** Dark mode (`#0E1117` background, `#00c0f2` accent)

### 11.1 Tab Structure

#### Synthetic / Production Mode (5–6 tabs)

| Tab | Component File | Content |
|---|---|---|
| 🗺️ Network Map | `topology_view.py` | Graphviz topology + health metrics |
| 🏭 Floor Plan | `floor_plan_view.py` | Spatial heatmap on factory floor image |
| 🌡️ Thermal Twin | `thermal_view.py` | Physics-based cable temperature view |
| 📊 System Performance | `validation_metrics.py` | AI accuracy metrics + confusion matrix |
| 🔒 Security | `security_view.py` | Rogue devices + config drift |
| 📡 Collectors | `collector_status.py` | SNMP/Modbus collector management |

#### Live Network Mode (5 tabs)

| Tab | Content |
|---|---|
| 🔴 Live Setup | Subnet scanner + device selector + start/stop |
| 🗺️ Network Map | Live topology + real-time health metrics |
| 🌡️ Thermal Twin | Physics-based failure predictions |
| 📊 AI Insights | Validation metrics |
| 🔒 Security | Security monitoring |

### 11.2 AI Chat Interface

**Module:** `src/intelligence/ai_assistant.py`, `src/dashboard/components/chat_interface.py`

A context-aware chat assistant embedded in the dashboard. The `AIAssistant` receives real-time context updates (current anomalies, KPI values, topology, predictions) on every dashboard render cycle and answers operator questions in natural language.

### 11.3 Auto-Refresh (Live Mode)

`streamlit-autorefresh` drives automatic page refresh at the configured poll interval when Live Network Mode is active:
```python
st_autorefresh(interval=poll_interval_ms, key="live_autorefresh")
```

---

## 12. Database Design

**Database:** TimescaleDB (PostgreSQL extension)  
**ORM:** SQLAlchemy  
**Validation:** Pydantic  
**Schema Location:** `src/database/`

### 12.1 Design Rationale

TimescaleDB was chosen over dedicated TSDBs (InfluxDB, Prometheus) because industrial network monitoring requires **joining time-series metric data with relational asset inventory** in a single query — a feature set not efficiently supported by pure TSDBs.

### 12.2 Key Tables

| Table | Type | Description |
|---|---|---|
| `assets` | Relational | Device inventory, metadata, topology |
| `metrics` | Hypertable (time-series) | All collected metric readings |
| `anomalies` | Relational + time-indexed | Detected anomaly events |
| `diagnoses` | Relational | AI diagnosis outputs |
| `configurations` | Relational | Device config snapshots |

### 12.3 Example Complex Query

```sql
-- Get devices with anomalous metrics in last 1 hour
SELECT a.name, a.location, m.metric_name, AVG(m.value) as avg_val
FROM assets a
JOIN metrics m ON a.asset_id = m.asset_id
WHERE m.timestamp > NOW() - INTERVAL '1 hour'
  AND m.metric_name = 'packet_loss'
GROUP BY a.name, a.location, m.metric_name
HAVING AVG(m.value) > 5.0
ORDER BY avg_val DESC;
```

---

## 13. Configuration & Deployment

### 13.1 Environment Variables (`.env`)

```env
# Database
TIMESCALEDB_HOST=localhost
TIMESCALEDB_PORT=5432
TIMESCALEDB_DB=nethealth
TIMESCALEDB_USER=admin
TIMESCALEDB_PASSWORD=<secret>

# SNMP
SNMP_COMMUNITY=public
SNMP_VERSION=3

# Dashboard
STREAMLIT_PORT=8501
```

### 13.2 Running the Dashboard

```bash
# Windows
start_dashboard.bat

# Linux/macOS
./start_dashboard.sh

# Direct
streamlit run src/dashboard/app.py --server.port 8501
```

### 13.3 Docker Deployment

```yaml
# docker-compose.yml
services:
  dashboard:
    build: .
    ports: ["8501:8501"]
  timescaledb:
    image: timescale/timescaledb:latest-pg14
    ports: ["5432:5432"]
```

### 13.4 System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Python | 3.9+ | 3.11+ |
| RAM | 4 GB | 8 GB |
| CPU | 2 cores | 4+ cores |
| Storage | 5 GB | 20 GB (for extended datasets) |
| GPU | None (optional) | CUDA-capable (for GNN/LSTM training) |

---

## 14. Performance Benchmarks & Validation

### 14.1 Quantitative Results

| Metric | Value | Test Set |
|---|---|---|
| **Diagnostic Accuracy** | **75.0%** | 100 diverse fault scenarios |
| **Detection Precision** | **75.4%** | 100 diverse fault scenarios |
| **Detection Recall** | ~73% | 100 diverse fault scenarios |
| **Diagnosis Latency** | < 1 second | Real-time monitoring window |
| **Live Scan Speed** | ~50 hosts/s | /24 subnet, 50 workers |
| **Bayesian Inference Time** | < 100 ms | Per anomaly event |

### 14.2 Validated Fault Scenarios

| Fault Type | Detection Rate | Correct Root Cause |
|---|---|---|
| Cable Failure (L1) | 82% | 78% |
| EMI Interference (L1) | 71% | 68% |
| Network Congestion (L3) | 79% | 74% |
| Config Error (L3/L4) | 68% | 65% |
| Application Fault (L7) | 75% | 73% |

### 14.3 The Cross-Layer Masquerade Test

A key validation scenario: a physical cable fault (L1) manifests purely as application response-time degradation (L7). The system was validated to trace through TCP retransmission increases (L4) and packet loss (L3) back to the originating CRC errors (L1), with the correct root cause (`CableFailure`) achieving the highest posterior probability in the Bayesian engine.

### 14.4 Granger Causality Validation

Statistical testing on synthetic data confirmed the following causal chains at p < 0.05:

- `temperature → crc_error` (lag 2)
- `crc_error → packet_loss` (lag 1)  
- `packet_loss → latency` (lag 1–2)
- `latency → response_time` (lag 2–3)

---

## 15. Dependency Reference

### 15.1 Core Dependencies

| Package | Version | Purpose |
|---|---|---|
| `streamlit` | ≥ 1.30 | Dashboard frontend |
| `pandas` | ≥ 2.0 | Data manipulation |
| `numpy` | ≥ 1.24 | Numerical computation |
| `scikit-learn` | ≥ 1.3 | Isolation Forest anomaly detection |
| `pgmpy` | ≥ 0.1.23 | Bayesian Network inference |
| `statsmodels` | ≥ 0.14 | Granger causality, ADF test |
| `pydantic` | ≥ 2.0 | Data validation models |
| `sqlalchemy` | ≥ 2.0 | Database ORM |

### 15.2 Industrial Protocol Stack

| Package | Protocol | Purpose |
|---|---|---|
| `pysnmp` | SNMP v3 | Managed device polling |
| `pymodbus` | Modbus TCP | PLC / industrial controller polling |

### 15.3 Deep Learning Stack

| Package | Purpose |
|---|---|
| `torch` | PyTorch — GNN and LSTM model runtime |
| `torch-geometric` | Graph Neural Network framework |

### 15.4 Visualization & Utilities

| Package | Purpose |
|---|---|
| `graphviz` | Network topology graph rendering |
| `plotly` | Interactive charts in dashboard |
| `streamlit-autorefresh` | Auto-refresh for live mode |

### 15.5 Installation

```bash
# Core requirements
pip install -r requirements.txt

# Full requirements (with deep learning)
pip install -r requirements/requirements-full.txt
```

---

*End of Technical Annexure — NetHealth AI v1.0*
