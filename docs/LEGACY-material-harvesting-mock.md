# Legacy: the Material Harvesting Mock

This was the repository README until 2026-10-22. It describes `app/`, a Streamlit
mock built by a collaborator, which an adversarial review (see
`ideas/permit-driven-material-surplus/`) recommended **BLOCK** as a product. The code
is kept for reference only; the shipped product is U-Shade. Text follows unchanged.

---

# Material Harvesting Engine
**The city already has everything it needs. We find it first.**

## What this is
An AI-powered urban material intelligence platform — the Uber for Materials.
It detects reusable materials across the city, classifies them with AI, predicts future availability,
matches supply to demand, optimises collection logistics, and supports designers with material-driven recommendations.

## The concept
Uber did not own cars. We do not own materials.
The city generates the supply. We find it, score it, and match it to the people who need it.

## Modules
1. Material Detection Dashboard — what the city has right now
2. AI Material Classifier — describe or photograph a material, get a harvest recommendation
3. Predictive Availability Engine — what the city will have in the next 90 days
4. Stakeholder Marketplace — connect owners, collectors, designers, and organizers
5. Logistics Optimiser — the most efficient collection route
6. Design Intelligence — available materials first, design second

## Quick start
```
python -m venv .venv
.venv\Scripts\Activate.ps1     (Windows)
pip install -r requirements.txt
cp .env.example .env            (add your Anthropic key if you have one)
streamlit run app/Home.py
```

## Run tests
```
python tests/test_core.py
```

## Architecture
```
app/  ->  src/  ->  config/
```
Services are pure Python. Streamlit is only in app/. No external routing APIs.
The LLM falls back to a deterministic offline engine when no API key is present.

## Business context
- Primary market: Barcelona summer festival circuit (Grec, Primavera, Sonar, Cruilla, Brunch Electronik)
- Secondary market: Ajuntament de Barcelona IMPUQV / Pla Clima programme (EUR 13M shade budget)
- Carbon benchmark: 120-180 kgCO2e/m2 avoided vs permanent shade civil works
