# 🌲 Arboric

**Intelligent autopilot for cloud infrastructure that schedules AI workloads during optimal energy windows to minimize cost and carbon emissions.**

[![PyPI version](https://img.shields.io/pypi/v/arboric.svg)](https://pypi.org/project/arboric/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## The Problem

AI teams spend millions on compute. Most of that cost is arbitrary - determined by *when* jobs run, not *what* they do. Spot and on-demand pricing fluctuate significantly across hours — windows that correlate with grid conditions. Carbon intensity varies substantially hour-to-hour. Yet nearly every workload runs immediately at peak cost.

Compliance is moving faster. [SB 253 (California's Scope 3 deadline)](https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320SB253) is **January 2027**. Most cloud platforms can't prove workload carbon - they need scheduling intelligence.

## The Solution

Arboric monitors spot instance pricing and marginal emissions rates independently, then automatically delays flexible workloads to the lowest-cost, lowest-carbon execution window within your deadline. An algorithm running on your own infrastructure (or ours).

- **Cost reduction** on flexible workloads (real metrics, not projections)
- **Scope 3 compliance** with audit trail showing carbon-aware decisions
- **Zero code changes** — works with any orchestration layer (Airflow, Kubernetes, serverless, etc.)
- **Deploy in hours** — single binary + REST API

---

## 🚀 Quick Start

### Install & Run

[View on PyPI →](https://pypi.org/project/arboric/)

```bash
pip install arboric

```bash
pip install arboric
arboric demo
```

That's it. See a live demo of cost and carbon optimization on your local grid region.

### CLI for Single Workloads

```bash
# Optimize a specific job: 6h, must finish within 24h
# Power is auto-derived from instance type, or defaults to 100 kW
arboric optimize "LLM Training" --duration 6 --deadline 24 --instance-type p3.8xlarge --provider aws

# See the grid forecast (prices + carbon intensity)
arboric forecast --region US-WEST --hours 24

# Explore cost-vs-carbon tradeoffs
arboric tradeoff "ETL" --duration 2 --deadline 12 --region US-WEST

# Project annual savings with frequency (daily, weekdays, weekly, monthly, or runs/week)
arboric optimize "Batch Job" --duration 4 --deadline 24 --frequency weekly
```

### Real Output

```
┌────────────────────────────────────────────────────────────┐
│                 SCHEDULE RECOMMENDATION                    │
├────────────────────────────────────────────────────────────┤
│  Run Immediately      vs    Delay to 1:00 PM               │
├────────────────────────────────────────────────────────────┤
│  Cost        $109.66              $64.09                   │
│  Carbon      328 kg               135 kg                   │
│  Deadline    OK ✓                 OK ✓                     │
├────────────────────────────────────────────────────────────┤
│  Recommendation: Delay 4 hours                             │
│  💰 Save $45.57  ·  🌱 Avoid 193.68 kg CO₂                 │
└────────────────────────────────────────────────────────────┘
```

---

## 🌐 REST API

Self-hosted or cloud-hosted. One HTTP request to get optimal start time + savings estimate.

### Start the API

```bash
arboric api --port 8000
```

Then visit **http://localhost:8000/docs** for interactive API explorer (Swagger UI).

### Endpoint Reference

**POST /api/v1/optimize** — Optimize one workload
```bash
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "workload": {
      "name": "Training Job",
      "duration_hours": 6,
      "power_draw_kw": 120,
      "deadline_hours": 24,
      "instance_type": "p3.8xlarge",
      "cloud_provider": "aws"
    },
    "region": "US-WEST",
    "runs_per_week": 1
  }'
```

Response includes:
- `region` — which region was optimized (or optimal region if "all" was specified)
- `optimization.optimal_start` — when to run (ISO 8601 timestamp)
- `optimization.delay_hours` — hours to delay from now
- `metrics.savings` — cost and carbon savings vs. immediate execution
- Supports annual projection with `runs_per_week` (frequency of job execution per week)

**POST /api/v1/fleet/optimize** — Optimize multiple workloads
```bash
curl -X POST http://localhost:8000/api/v1/fleet/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "workloads": [
      {"name": "Job A", "duration_hours": 2, "power_draw_kw": 50, "deadline_hours": 12},
      {"name": "Job B", "duration_hours": 4, "power_draw_kw": 100, "deadline_hours": 24}
    ],
    "region": "US-WEST"
  }'
```

Returns aggregated savings + per-workload schedules.

**GET /api/v1/forecast** — Raw grid data
```bash
curl "http://localhost:8000/api/v1/forecast?region=US-WEST&hours=24"
```

Returns hourly forecast with:
- `price` — Spot instance price ($/hour)
- `co2_intensity` — Carbon intensity (gCO₂/kWh)
- `renewable_percentage` — Renewable energy penetration
- `timestamp` — Forecast window start time

**GET /api/v1/health** — Health check
```bash
curl http://localhost:8000/api/v1/health
```

**GET /api/v1/status** — API + configuration status
```bash
curl http://localhost:8000/api/v1/status
```

### Integration Example (Python)

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

# Get optimal schedule
response = client.post("/api/v1/optimize", json={
    "workload": {
        "name": "Model Training",
        "duration_hours": 8,
        "power_draw_kw": 200,
        "deadline_hours": 24,
        "instance_type": "p3.8xlarge",
        "cloud_provider": "aws"
    },
    "region": "US-WEST",
    "runs_per_week": 1  # For annual savings projection
})

result = response.json()
data = result['data']
print(f"Region: {data['region']}")
print(f"Delay: {data['optimization']['delay_hours']} hours")
print(f"Save: ${data['metrics']['savings']['cost']:.2f}")
print(f"Annual savings: ${data['metrics']['savings'].get('annual_cost_savings', 0):.2f}")
```

Works with any orchestration (Airflow DAGs, Kubernetes Jobs, Lambda, etc.).

### Annual Savings Projection

To estimate annual savings, provide `runs_per_week` in your request. Arboric will multiply per-run savings by frequency:

**CLI:**
```bash
arboric optimize "Batch Job" --frequency daily        # 365 runs/year
arboric optimize "Batch Job" --frequency weekly       # 52 runs/year
arboric optimize "Batch Job" --frequency monthly      # 12 runs/year
arboric optimize "Batch Job" --frequency 5            # 5 runs/week = 260/year
```

**API:**
Pass `runs_per_week` in your request. Response includes:
- `metrics.savings.annual_cost_savings` — Projected annual savings
- `metrics.savings.annual_projection_basis` — Frequency used for calculation

---

## ⚡ Core Features

- **Algorithm** — Simple rolling-window cost-carbon optimization (70% cost / 30% carbon by default, adjustable)
- **Deadline-aware** — Respects job deadlines, finds optimal start times within constraints
- **Grid regions** — Pre-configured profiles for US-WEST, US-EAST, EU-WEST, NORDIC (carbon/price patterns learned from real grid data)
- **Fleet scheduling** — Optimize multiple jobs together or independently
- **Real grid data** — MockGrid (realistic simulation) or live API (requires `pip install arboric[cloud]`)
- **Instance-aware** — Auto-derives power consumption from cloud instance types (AWS, GCP, Azure)
- **Frequency projections** — Project annual savings with human-readable frequency presets (daily, weekdays, weekly, monthly)
- **Region tracking** — Clearly displays which region optimization used; supports cross-region comparison with `--region all`
- **Multi-output** — CLI, REST API, JSON/CSV exports for metrics tracking
- **Type-safe** — Full Python type hints + Pydantic validation

---

## 📊 Historical Analysis & Compliance

### `arboric history` — Optimization Audit Trail
Track all optimization decisions over time. Store in SQLite (scales to Postgres).

```bash
arboric history --since 30  # Last 30 days
arboric history --region US-WEST --limit 50
```

Returns:
- Which jobs were optimized and when
- Actual grid prices + carbon used
- Cost/carbon savings achieved
- Optimization timestamp + region

**Use case:** Show CFO proof of savings. Export monthly reports for stakeholder reviews.

### `arboric insights` — ROI & Trends Analysis
Aggregate historical optimizations to reveal savings patterns and opportunities.

```bash
arboric insights
```

Shows:
- **Total savings YTD** — Cost + carbon across all jobs
- **Best region** — Which grid region delivered highest savings
- **Top workload** — Which job type saved most money
- **Savings trajectory** — Trend over time (daily/weekly/monthly)
- **Carbon avoided** — Total kg CO₂ displaced

**Use case:** Board presentations. Prove optimization impact to finance/sustainability teams.

### Certified Carbon Receipt (Enterprise)
Generate tamper-evident PDF per job with cryptographic signature for compliance.

```bash
arboric optimize "Training Job" --receipt report.pdf
```

Includes:
- **Carbon intensity data** — Real-time marginal emissions rate from an external emissions provider
- **Compute cost snapshot** — Estimated savings from optimal scheduling vs. immediate execution
- **Execution details** — Job start time, duration, power, region
- **Savings proof** — Cost + carbon savings with supporting numbers
- **Audit signature** — Cryptographic hash for tamper detection
- **Compliance ready** — Audit trail for SB 253 Scope 3 reporting

**Use case:** Provide compliance artifacts to CFO/legal. Prove carbon-aware scheduling to auditors. Required for enterprise deals.

---

## 🏗️ How It Works

Arboric doesn't predict the future or use ML. It uses real grid data (or realistic simulation) to find the cheapest, cleanest execution window within your deadline.

**The Algorithm**

1. **Load grid forecast** — Get 48-hour compute pricing signals + carbon intensity for your region
2. **Find all feasible windows** — Scan every possible start time that meets your deadline
3. **Score each window** — Calculate estimated compute cost × (70%) + carbon × (30%), normalized
4. **Pick the best** — Return the schedule that minimizes your composite score
5. **Calculate savings** — Show estimated compute cost $/kg CO₂ saved vs. running now

All of this runs in <100ms per workload. No external calls (unless you enable live grid data).

**Real Example**

_Cost signal: normalized regional compute pricing index. Carbon: grid intensity g/kWh._

```
Grid (US-WEST, 6-hour job, 120 kW)

Hour    Cost Signal    Carbon    Score
08:00   $0.150   420 g     67.2  ← running now
09:00   $0.145   410 g     64.5
10:00   $0.120   350 g     50.1
11:00   $0.095   280 g     39.8
12:00   $0.085   200 g     30.1  ← BEST (cost + carbon combo)
13:00   $0.088   190 g     30.5

Result: Delay 4 hours
  • Cost: $110.66 → $61.20 (save $49.46)
  • Carbon: 350 kg → 140 kg (avoid 210 kg)
  • Deadline: 24h available, job uses 6h ✓
```

---

## 🏛️ Architecture

```
arboric/
├── arboric/
│   ├── cli/
│   │   └── main.py              # Typer CLI (optimize, demo, api, forecast, config)
│   ├── api/
│   │   ├── main.py              # FastAPI app + docs
│   │   ├── routes/              # /optimize, /fleet/optimize, /forecast, /status, /config
│   │   └── models/              # Request/response schemas
│   └── core/
│       ├── models.py            # Pydantic data models (Workload, ScheduleResult, etc)
│       ├── autopilot.py         # Rolling-window optimization algorithm
│       ├── grid_oracle.py       # Grid forecasting (duck curve, TOU pricing)
│       ├── config.py            # Config file loading
│       └── constraints.py       # Deadline/resource validation
├── site/                        # Single-file React marketing site
├── tests/                       # pytest suite with full coverage
├── pyproject.toml
├── config.yaml                  # Configuration example
└── README.md
```

**Key Modules**

- **[autopilot.py](arboric/core/autopilot.py)** — Rolling-window algorithm. Scans all feasible start times, scores each (cost + carbon), picks the minimum.
- **[grid_oracle.py](arboric/core/grid_oracle.py)** — Realistic grid simulation: duck curve (solar dip), evening ramp, night baseline. Regional profiles. Seed-deterministic for demos.
- **[models.py](arboric/core/models.py)** — Pydantic types: `Workload`, `GridWindow`, `ScheduleResult`, `OptimizationConfig`.
- **[main.py (CLI)](arboric/cli/main.py)** — Typer commands: `optimize` (single job), `demo` (interactive), `api` (server), `forecast` (grid data), `config` (settings).
- **[main.py (API)](arboric/api/main.py)** — FastAPI server with 5 endpoints + Swagger docs.

---

## 📦 Installation and Setup

### Requirements
- Python 3.10 or higher
- pip package manager

### Install from PyPI
```bash
pip install arboric
```

### Install for Development
```bash
# Clone the repository
git clone https://github.com/aashanm/arboric.git
cd arboric

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run type checking
mypy arboric

# Run linting
ruff check arboric
```

---

## ⚙️ Configuration

Store defaults in `~/.arboric/config.yaml` instead of typing CLI flags every time.

### Quick Setup

```bash
arboric config init      # Create default ~/.arboric/config.yaml
arboric config show      # View current config
arboric config edit      # Edit in your $EDITOR
```

### Configuration File

See [config.yaml](config.yaml) for the full example. Key settings:

```yaml
optimization:
  cost_weight: 0.7      # Cost vs. carbon tradeoff (0-1)
  carbon_weight: 0.3    # Must sum to 1.0

defaults:
  duration_hours: 6.0   # Used if --duration not specified
  deadline_hours: 24.0  # Used if --deadline not specified
  region: US-WEST       # US-WEST, US-EAST, EU-WEST, NORDIC
  instance_type: null   # Cloud instance (e.g., p3.8xlarge); auto-derives power
  cloud_provider: null  # aws, gcp, or azure

cli:
  show_banner: true
  quiet_mode: false

# Live grid data (optional; requires pip install arboric[cloud])
live_data:
  enabled: false
  # api_key: ""
```

**Usage:**

```bash
# Uses config defaults
arboric optimize "My Job"

# Override specific values
arboric optimize "My Job" --duration 8 --region EU-WEST

# Specify instance type to auto-derive power consumption
arboric optimize "Training" --instance-type p3.8xlarge --provider aws
```

---

## 🧪 Testing & Quality

```bash
# Run tests with coverage
pytest

# Type checking
mypy arboric

# Linting + formatting
ruff check arboric
ruff format arboric
```

---

## 💰 Why Now

**Market Timing**
- **SB 253** (Scope 3 reporting): Jan 2027 deadline. AI/cloud companies need provable carbon-aware scheduling to report compliance.
- **Cost pressure**: AI training budgets are huge. Every 1% cost reduction = millions saved. Cloud cost arbitrage is a proven lever.
- **Grid data availability**: Real-time carbon/price APIs make this possible at scale.

**Why We Win**
- **Simple**: One HTTP endpoint. No orchestration changes. No ML.
- **Portable**: Works with Airflow, Kubernetes, Lambda, Prefect, Dagster—any scheduler.
- **Compliant**: Audit trail of carbon-aware decisions. Export JSON for Scope 3 reporting.
- **Efficient**: Algorithm runs in <100ms. Mock or real grid data. Extensible to custom cost models.

---

## 📄 License

Arboric is released under the [MIT License](LICENSE).

---

## Getting Help

- **Package:** [PyPI Listing](https://pypi.org/project/arboric/)
- **Questions?** Open an issue on [GitHub](https://github.com/aashanm/arboric)
- **Want to contribute?** PRs welcome.
- **Feedback?** Reach out to am@arboric.xyz or arr@arboric.xyz.
