# Arboric Project Intelligence

## Project Structure
This is a monorepo with two domains:
- `arboric/` — Python backend (CLI, API, optimization engine)
- `site/` — Marketing website (single-file React)

Apply rules contextually based on which part of the codebase you're working in.

## Skills
- Load .claude/skills/arboric-brand.md ONLY when working in site/ or on any copy/messaging task
- Do NOT apply brand/messaging rules when working on backend Python code

## Backend Rules (arboric/)
- Python 3.10+, type hints everywhere
- Pydantic models for all data structures
- FastAPI for API layer
- Follow existing patterns in models.py, autopilot.py, grid_oracle.py
- Test with pytest
- Lint with ruff, type-check with mypy

## Frontend Rules (site/)
- Single-file React .jsx — no build pipeline, no framework, ships today
- Tailwind core utility classes only (no compiler)
- Dark mode default
- The site sells OUTCOMES (save money, stay compliant), not MECHANISMS
- Target: VP Eng and FinOps who skim. Every section scannable in 5 seconds.
- Mobile responsive
- Deterministic output: seed all randomness so every visitor sees same demo

## Shared Constants (backend is source of truth)
- All grid math constants come from grid_oracle.py REGION_PROFILES
- Default optimization weights: 70% cost / 30% carbon
- Price normalization ceiling: $0.30/kWh
- Carbon normalization ceiling: 600 gCO2/kWh
- If the website shows a number, it must be traceable to the Python codebase

## Key Business Numbers (from ANALYSIS.md)
- Typical savings: 30-60% cost, 40-60% carbon
- Reference demo: 6h @ 120kW, saves $45.57 (41.5%) and 193.68kg CO2 (59.0%)
- Performance fee: 20% of realized savings
- SB 253 Scope 3 deadline: January 2027

## Code Quality (all code)
- Accessible: aria-labels on interactive elements (frontend)
- React.memo() on expensive components, debounce inputs 150ms (frontend)
- Docstrings on all public functions (backend)
- No hardcoded magic numbers — reference constants
