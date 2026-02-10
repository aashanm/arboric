# 🌲 Arboric

**Intelligent autopilot for cloud infrastructure that schedules AI workloads during optimal energy windows to minimize cost and carbon emissions.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 🎯 Problem

Data centers running AI training jobs and batch workloads consume massive amounts of electricity, often at the worst possible times. Running compute-heavy workloads during peak hours means:
- **💸 Higher costs** from time-of-use pricing spikes
- **🏭 More carbon emissions** when the grid relies on fossil fuels
- **⚡ Grid strain** during demand surges

## ✨ Solution

Arboric is an intelligent scheduling autopilot that analyzes electricity grid forecasts and automatically delays flexible workloads to run during:
- **Solar peak hours** when renewable energy floods the grid
- **Off-peak periods** when electricity prices drop
- **Low-carbon windows** when grid intensity is minimal

**Result:** Slash both your electricity bills and carbon footprint without changing a single line of your application code.

---

## 🚀 Quick Start

```bash
# Install Arboric
pip install arboric

# Optimize a single workload
arboric optimize "LLM Training" --duration 6 --deadline 24 --power 120

# Run the interactive demo
arboric demo

# View grid forecast
arboric forecast --region US-WEST --hours 24
```

**Example output:**
```
┌────────────────────────────────────────────────────────────┐
│                   OPTIMIZATION ANALYSIS                    │
├────────────────────────────────────────────────────────────┤
│  Metric          Immediate Run    Arboric Schedule  Yield  │
├────────────────────────────────────────────────────────────┤
│  Start Time      09:00           13:00              +4.0h  │
│  Avg Price       $0.1523/kWh     $0.0891/kWh        -41.5% │
│  Avg Carbon      456 gCO2/kWh    187 gCO2/kWh       -59.0% │
│                                                             │
│  Total Cost      $109.66         $64.09             -$45.57│
│  Total Carbon    328.32 kg       134.64 kg          -193.68│
└────────────────────────────────────────────────────────────┘

💰 $45.57 saved  ·  🌱 193.68 kg CO₂ avoided
```

---

## ⚡ Features

### Core Capabilities
- **🧠 Smart Scheduling:** Algorithmic optimization balances cost and carbon trade-offs
- **📊 Grid Forecasting:** Simulates realistic electricity grid behavior (duck curve, TOU pricing)
- **⏰ Deadline Awareness:** Respects workload deadlines while maximizing efficiency
- **🌍 Multi-Region:** Supports US-WEST, US-EAST, EU-WEST, NORDIC grid profiles
- **🔮 Fleet Optimization:** Schedule multiple workloads across a 24-48h horizon

### Developer Experience
- **🎨 Beautiful CLI:** Rich terminal UI with colors, tables, and live progress
- **🐍 Python API:** Programmatic access for automation and integration
- **✅ Type-Safe:** Full Pydantic validation for workload definitions
- **📦 Zero Config:** Works out-of-the-box with sensible defaults

---

## 🏗️ How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     ARBORIC WORKFLOW                        │
└─────────────────────────────────────────────────────────────┘

    1. WORKLOAD DEFINITION
    ┌──────────────────────┐
    │  Duration: 6 hours   │
    │  Power: 120 kW       │
    │  Deadline: 24 hours  │
    └──────────┬───────────┘
               │
               ▼
    2. GRID FORECAST ANALYSIS
    ┌─────────────────────────────────────────────────────┐
    │  Hour  │ Carbon (g) │ Price ($) │ Score              │
    ├─────────────────────────────────────────────────────┤
    │  09:00 │    456     │  0.1523   │  67.2  ◄── Now    │
    │  10:00 │    398     │  0.1345   │  58.1             │
    │  11:00 │    287     │  0.1012   │  41.8             │
    │  12:00 │    214     │  0.0876   │  32.5             │
    │  13:00 │    187     │  0.0891   │  30.1  ◄── Best!  │
    │  14:00 │    203     │  0.0923   │  32.8             │
    └─────────────────────────────────────────────────────┘
               │
               ▼
    3. OPTIMIZATION ENGINE
    ┌────────────────────────────────────┐
    │  Rolling window algorithm:         │
    │  • Scan all feasible start times   │
    │  • Calculate cost + carbon score   │
    │  • Weight: 70% cost, 30% carbon    │
    │  • Find minimum composite score    │
    └────────────┬───────────────────────┘
                 │
                 ▼
    4. SCHEDULE RESULT
    ┌──────────────────────────────────────┐
    │  ✅ Delay by 4 hours                 │
    │  💰 Save $45.57 (41.5%)              │
    │  🌱 Avoid 193.68 kg CO₂ (59.0%)      │
    └──────────────────────────────────────┘
```

---

## 🏛️ Architecture

```
arboric/
├── arboric/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py              # Typer CLI interface
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py            # Pydantic data models
│   │   ├── autopilot.py         # Optimization algorithm
│   │   └── grid_oracle.py       # Grid forecast simulation
│   └── integrations/
│       ├── __init__.py
│       └── watttime.py          # Future: Real API integration
├── tests/
│   ├── test_models.py
│   ├── test_autopilot.py
│   └── test_grid_oracle.py
├── pyproject.toml
├── README.md
└── LICENSE
```

### Key Components

**Core Models** ([models.py](arboric/core/models.py))
- `Workload`: Defines compute jobs with duration, power draw, deadline
- `GridWindow`: Represents grid state (carbon intensity, price, renewables)
- `ScheduleResult`: Optimization output with savings metrics

**Optimization Engine** ([autopilot.py](arboric/core/autopilot.py))
- Rolling-window algorithm scans feasible execution times
- Composite scoring: weighted combination of cost and carbon
- Respects deadlines and priority levels

**Grid Oracle** ([grid_oracle.py](arboric/core/grid_oracle.py))
- Simulates realistic grid behavior with duck curve dynamics
- Regional profiles for US-WEST, US-EAST, EU-WEST, NORDIC
- Future: Integration with WattTime API, ISO market data

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
git clone https://github.com/arboric/arboric.git
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

## 💻 Usage Examples

### Command-Line Interface

**Optimize a single workload:**
```bash
arboric optimize "Daily ETL Pipeline" \
  --duration 2 \
  --deadline 12 \
  --power 40 \
  --region US-WEST
```

**View grid forecast:**
```bash
arboric forecast --region EU-WEST --hours 48
```

**Run the demo:**
```bash
arboric demo
```

**Check system status:**
```bash
arboric status
```

---

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=arboric --cov-report=html

# Run specific test file
pytest tests/test_autopilot.py

# Run with verbose output
pytest -v
```

### Code Quality Checks
```bash
# Type checking
mypy arboric

# Linting
ruff check arboric

# Formatting
ruff format arboric
```

---

## 📄 License

Arboric is released under the [MIT License](LICENSE).

---

## 🙏 Acknowledgments

- Regional grid profiles based on CAISO, ERCOT, and EIA data

---

**Built with 🌱 for a sustainable future.**
