<p align="center">
  <img src="docs/logo_neosis.png" alt="Noesis" width="200">
</p>

# Noesis

> **Predicting the unpredictable. Accelerating breakthroughs through autonomous, agent-driven discovery loops.**

**A Hack-Nation 7th Edition Submission by Team EigenBrains**
**Challenge 03 — 10× Faster Scientific Discovery**

---

## 🚀 The Moonshot

**What if an AI laboratory could discover when an optimization algorithm is about to fail — and intervene before it actually does?**

**Noesis** is an autonomous AI laboratory designed to accelerate scientific discovery by turning the traditional scientific method into a continuous, agent-driven discovery loop.

Instead of relying on a researcher to manually:

1. inspect results,
2. formulate hypotheses,
3. design experiments,
4. run simulations,
5. analyze outcomes, and
6. decide what to test next,

Noesis delegates these steps to specialized AI agents coordinated through **Omnigent**.

The result is a closed-loop research system:

```text
        ┌───────────────────────┐
        │   Scientific Insight  │
        │      & Hypothesis     │
        └───────────┬───────────┘
                    ↓
        ┌───────────────────────┐
        │   Experiment Planner  │
        └───────────┬───────────┘
                    ↓
        ┌───────────────────────┐
        │    Experiment Runner  │
        │   Simulations / Data  │
        └───────────┬───────────┘
                    ↓
        ┌───────────────────────┐
        │    Analysis Agent     │
        │ Evidence & Evaluation │
        └───────────┬───────────┘
                    │
                    └──────────────► New Hypothesis
```

**Hypothesis → Experiment → Evidence → Insight → New Hypothesis**

This transforms Noesis from a simple AI assistant into an **autonomous discovery loop**.

---

# 🔬 Our Scientific Question

We focus on a fundamental problem in evolutionary and population-based optimization:

> **Can the dynamics of population entropy predict an impending search collapse before fitness stagnation becomes obvious — and can that early-warning signal trigger an intervention that recovers the optimum faster on unseen and dynamically shifting landscapes?**

Population-based optimization algorithms can gradually lose diversity.

When this happens:

```text
High Diversity
      │
      ▼
Exploration
      │
      ▼
Population Convergence
      │
      ▼
Entropy Collapse
      │
      ▼
Search Becomes Trapped
      │
      ▼
Fitness Stagnation
```

The key idea behind Noesis is simple:

> **Fitness stagnation may be a symptom. Population entropy collapse may be an early warning signal.**

If entropy can reliably identify an approaching search collapse **before** fitness stagnates, an autonomous agent could intervene early and redirect the search.

---

# 🎯 The Noesis Hypothesis

We hypothesize that:

> **A significant decline in population entropy precedes observable fitness stagnation and can therefore serve as an early-warning signal for optimization collapse.**

Noesis attempts to learn:

* when population diversity becomes dangerously low,
* whether an entropy threshold generalizes across landscapes,
* how early the collapse can be detected,
* which intervention is most effective,
* and whether predictive intervention improves recovery time on unseen and dynamically shifting landscapes.

The ultimate objective is not simply to find a better solution.

It is to **discover the conditions under which the search itself is about to fail — and correct it autonomously.**

---

# 🧪 From Manual Optimization to Autonomous Discovery

### Traditional workflow

```text
Researcher
    │
    ├── Inspect results
    ├── Form hypothesis
    ├── Design experiment
    ├── Run simulation
    ├── Analyze results
    └── Repeat
```

### Noesis

```text
┌──────────────────────────────────────────────────────┐
│                    NOESIS LAB                        │
│                                                      │
│  Insight → Plan → Experiment → Analysis → Insight   │
│     ▲                                      │         │
│     └──────────────────────────────────────┘         │
│                                                      │
└──────────────────────────────────────────────────────┘
```

The researcher defines the scientific objective.

**Noesis manages the discovery loop.**

---

# 🧠 Agentic Orchestration

Noesis uses specialized agents rather than asking a single model to perform the entire research process.

All agents collaborate through a **shared research record**, allowing experimental evidence to influence subsequent decisions.

## 1. 🔎 Insight Agent

The scientific reasoning layer.

Responsibilities:

* analyzes previous experimental evidence,
* identifies patterns,
* proposes testable hypotheses,
* estimates the entropy threshold associated with collapse,
* proposes candidate interventions.

**Output:** a falsifiable scientific hypothesis.

---

## 2. 🧭 Experiment Planner

The experimental-design layer.

Responsibilities:

* translates hypotheses into experiments,
* selects appropriate benchmark landscapes,
* chooses parameter configurations,
* introduces dynamically shifting environments,
* prioritizes experiments that provide the most informative evidence.

**Output:** a structured experimental plan.

---

## 3. ⚙️ Experiment Runner

The execution layer.

Responsibilities:

* executes Python simulations,
* runs baseline optimization,
* runs the predictive intervention strategy,
* maintains matched experimental conditions,
* records population entropy and fitness dynamics.

**Output:** reproducible experimental data.

---

## 4. 📊 Analysis Agent

The evidence layer.

Responsibilities:

* evaluates experimental outcomes,
* compares baseline and intervention strategies,
* measures recovery time,
* identifies successful and failed interventions,
* extracts evidence for the next research cycle.

**Output:** structured evidence and updated research context.

---

# 🔁 The Autonomous Discovery Loop

```text
                    ┌─────────────────┐
                    │  Insight Agent  │
                    │   Hypothesis    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Experiment      │
                    │ Planner         │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Experiment      │
                    │ Runner          │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Analysis Agent  │
                    │    Evidence     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Updated Research│
                    │     Record      │
                    └────────┬────────┘
                             │
                             └──────────────► Insight Agent
```

Each cycle makes the next experiment more informed by the evidence collected previously.

---

# 📈 What We Measure

Noesis evaluates discovery acceleration through measurable optimization dynamics.

### Population-level signals

* **Population entropy**
* Population diversity
* Convergence dynamics
* Search-space coverage

### Optimization performance

* Best fitness
* Fitness stagnation
* Time to recovery
* Time to optimum / near-optimum
* Performance degradation after landscape shifts

### Scientific discovery metrics

* Hypothesis success rate
* Number of experiments required
* Experimental efficiency
* Generalization to unseen landscapes
* Improvement over the baseline strategy

The central comparison is:

```text
                    Optimization Performance

Baseline       ────────────────────────────────╮
                                                │
                                                │ stagnation
                                                ▼
Predictive     ────────────────╮
Intervention                   │ early warning
                               ▼
                         Intervention
                               │
                               ▼
                         Search Recovery
```

---

# 🌍 Dynamic Benchmark Landscapes

To avoid overfitting the discovery to a single static environment, Noesis evaluates its hypothesis across mathematical optimization landscapes, including dynamically shifting variants of:

* **Ackley**
* **Rastrigin**
* other configurable benchmark environments

The objective is to determine whether the learned warning signal remains useful when the search environment changes.

A successful discovery therefore needs to demonstrate more than:

> "This threshold works on one benchmark."

It should answer:

> **"Does this phenomenon generalize?"**

---

# 🏗️ Project Architecture

The repository separates the autonomous orchestration layer, scientific simulation environment, frontend visualization, and experimental evidence.

```text
.
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   ├── tools/
│   │   └── ...
│   ├── benchmarks/
│   ├── tests/
│   ├── EXPERIMENTS.md
│   └── pytest.ini
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── ...
│
├── benchmark/
│   ├── cases/
│   ├── configs/
│   ├── artifacts/
│   └── reports/
│
├── docs/
│   ├── API_CONTRACTS.md
│   └── BENCHMARK_METHODOLOGY.md
│
├── .env.example
└── README.md
```

## `backend/`

The Python engine powering the autonomous laboratory.

### `app/`

Core application logic, Omnigent orchestration, agent definitions, and research tools.

### `benchmarks/`

Simulation and optimization benchmark implementations.

### `EXPERIMENTS.md`

A living research log containing the experiments conducted by the autonomous discovery loop.

### `tests/`

Automated tests ensuring backend reliability and reproducibility.

---

## `frontend/`

Interactive dashboard built with:

* **Vite**
* **React**
* **TypeScript**

The interface provides a real-time window into the scientific process, including:

* agent handoffs,
* experiment status,
* population entropy,
* fitness evolution,
* recovery metrics,
* research-loop progression.

---

## `benchmark/`

Scientific evaluation environment.

### `cases/`

Benchmark landscapes and experimental scenarios.

### `configs/`

Experiment configurations and parameter definitions.

### `artifacts/`

Raw and structured outputs generated by experiments.

### `reports/`

Processed experimental results and analysis.

---

## `docs/`

System and methodology documentation.

### `API_CONTRACTS.md`

Defines communication interfaces between the frontend and backend.

### `BENCHMARK_METHODOLOGY.md`

Documents the mathematical framework, evaluation methodology, and metrics used to measure discovery acceleration.

---

# 🛠️ Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/Agentic-Scientific-Discovery-EigenBrains.git

cd Agentic-Scientific-Discovery-EigenBrains
```

## 2. Configure the environment

Create your local environment configuration from the provided template:

```bash
cp .env.example .env
```

Then configure the required API keys and Omnigent-related credentials.

> **Never commit API keys or secrets to the repository.**

---

## 3. Set up the backend

```bash
cd backend

python -m venv .venv
```

### Linux / macOS

```bash
source .venv/bin/activate
```

### Windows

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the backend according to the configuration described in the project documentation.

---

## 4. Start the frontend

From the project root:

```bash
cd frontend

npm install
npm run dev
```

The Vite development server will provide the Noesis research dashboard.

---

# 🧬 Why Noesis?

Most optimization systems focus on answering:

> **"What is the best solution?"**

Noesis asks a different question:

> **"Can we predict when our search process is about to stop finding better solutions?"**

That distinction is fundamental.

Instead of waiting for an optimization algorithm to fail, Noesis attempts to identify the **precursors of failure** and use them to trigger autonomous intervention.

This creates a new feedback loop:

```text
Optimization
     ↓
Observe Search Dynamics
     ↓
Detect Early Warning Signal
     ↓
Predict Collapse
     ↓
Intervene
     ↓
Recover Search
     ↓
Learn From Evidence
     ↓
Improve Next Experiment
```

---

# ⚡ Toward 10× Faster Scientific Discovery

Noesis does not define "10× faster" simply as making one simulation execute ten times faster.

Instead, we target the **scientific discovery process itself**.

The long-term vision is to reduce the number of human-driven iterations required to move from:

```text
Question
   ↓
Hypothesis
   ↓
Experiment
   ↓
Evidence
   ↓
New Hypothesis
```

to a system where this loop can operate continuously and autonomously.

### The ambition

**10× more experiments.**
**10× faster hypothesis iteration.**
**10× less manual scientific orchestration.**

Not by removing scientists from the loop—

**but by giving them an autonomous laboratory capable of exploring the space between their questions.**

---

# 🧪 Research Status

Noesis is currently focused on validating the core hypothesis around **population entropy as an early-warning signal for optimization collapse**.

The experimental loop is designed to progressively answer:

| Question                                          | Goal                       |
| ------------------------------------------------- | -------------------------- |
| Does entropy collapse precede fitness stagnation? | Validate the signal        |
| Is there a measurable tipping point?              | Identify the threshold     |
| Can an intervention exploit the signal?           | Validate causality         |
| Does it improve recovery time?                    | Measure acceleration       |
| Does it generalize across landscapes?             | Test robustness            |
| Can agents discover this autonomously?            | Validate the research loop |

---

# 👥 Team EigenBrains

**Noesis** is developed by **Team EigenBrains** for the **Hack-Nation 7th Global AI Hackathon**.

### Challenge

**Challenge 03 — 10× Faster Scientific Discovery**

### Core technologies

`Python` · `React` · `TypeScript` · `Vite` · `Omnigent` · `AI Agents` · `Optimization` · `Scientific Computing`

---

# 📚 Documentation

For deeper technical details:

* [`EXPERIMENTS.md`](backend/EXPERIMENTS.md) — Autonomous experiment history
* [`BENCHMARK_METHODOLOGY.md`](docs/BENCHMARK_METHODOLOGY.md) — Evaluation methodology
* [`API_CONTRACTS.md`](docs/API_CONTRACTS.md) — Frontend/backend interfaces

---

# 🔭 The Vision

Scientific discovery is fundamentally a search problem.

The search space is enormous.
Experiments are expensive.
Human attention is limited.

Noesis explores a future where AI does not merely **answer scientific questions**.

It learns how to **ask better questions, design better experiments, interpret evidence, and decide what to investigate next.**

> **Noesis doesn't replace the scientific method.**
>
> **It puts the scientific method on an autonomous loop.**

---

**Built by Team EigenBrains · Hack-Nation 7th Global AI Hackathon · Challenge 03**
