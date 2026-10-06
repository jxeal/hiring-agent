# AI Resume Screening & Ranking System

> **Role Target:** SDE Intern + AI background  
> **Evaluation Model:** Deterministic Hard Filter + 100-Point Explainable AI Ranking Model  
> **Interface:** Batch CLI (`main.py`) & Single Evaluator (`score.py`)

An automated, explainable resume evaluation pipeline that ingests a directory of candidate resumes, applies deterministic hard eligibility filters (Python + AI/agentic systems), enriches eligible candidates using public GitHub signals, scores candidates across a 100-point rubric with project-quality penalties, and produces a ranked shortlist in structured JSON.

---

## 📑 Table of Contents
- [How It Works](#how-it-works)
- [Input & Output Specification](#input--output-specification)
  - [Input: Resume Directory](#input-resume-directory)
  - [Output: Ranked JSON](#output-ranked-json)
  - [Terminal Batch Summary](#terminal-batch-summary)
- [Scoring Rubric & Rules](#scoring-rubric--rules)
  - [Hard Eligibility Filter](#1-hard-eligibility-filter-mandatory)
  - [100-Point Candidate Ranking](#2-100-point-candidate-ranking-eligible-only)
- [Installation & Setup](#installation--setup)
- [How to Run](#how-to-run)
  - [Batch Screening & Ranking](#1-batch-screening--ranking-all-resumes)
  - [Single Resume Evaluation](#2-single-resume-evaluation)
- [Design Decisions](#design-decisions)
- [If I Had More Time](#if-i-had-more-time)
- [Credits & Acknowledgements](#credits--acknowledgements)

---

## ⚙️ How It Works

```
                        [ ./resume/*.pdf ]
                                │
                                ▼
                   ┌───────────────────────────┐
                   │  1. PyMuPDF Text Parser   │
                   └─────────────┬─────────────┘
                                 │
                                 ▼
                   ┌───────────────────────────┐
                   │ 2. Section Extraction LLM │
                   │  (Basics, Work, Projects) │
                   └─────────────┬─────────────┘
                                 │
                                 ▼
                   ┌───────────────────────────┐
                   │ 3. Hard Eligibility Check │
                   │  (Python + AI/Agentic)    │
                   └─────────────┬─────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
          [ ❌ INELIGIBLE ]               [ ✅ ELIGIBLE ]
          - eligible: false                      │
          - total_score: 0                       ▼
          - rejection_reasons: [...]  ┌───────────────────────────┐
                                      │ 4. GitHub REST Enrichment │
                                      │    (commits, repos, PRs)  │
                                      └──────────┬────────────────┘
                                                 │
                                                 ▼
                                      ┌───────────────────────────┐
                                      │ 5. LLM Semantic Scoring   │
                                      │    (100-point rubric with │
                                      │     thin-wrapper penalty) │
                                      └──────────┬────────────────┘
                                                 │
                                                 ▼
                                      ┌───────────────────────────┐
                                      │ 6. Ranking & Shortlist    │
                                      │    (Saved to results.json)│
                                      └───────────────────────────┘
```

1. **Document Ingestion:** Ingests all candidate PDFs from the input directory. Malformed or unreadable resumes are caught gracefully without terminating the batch.
2. **Section Extraction:** Parses resume structure into standard fields (skills, projects, work experience, GitHub profiles).
3. **Deterministic Hard Filter:** Rejects candidates who lack genuine Python evidence or meaningful AI/agentic exposure before ranking.
4. **GitHub Enrichment:** If a candidate provides a GitHub link, fetches recent commit velocity, maintained repositories, and AI/Python repositories.
5. **Semantic Evaluation:** Evaluates project depth, backend fundamentals, cloud usage, and engineering practices using LLMs (Gemini / Ollama) constrained by structured output schemas.
6. **Incremental Saving & Ranking:** Saves each candidate's record as it completes and sorts the final list by score descending.

---

## 📦 Input & Output Specification

### Input: Resume Directory
Place PDF resumes into an input folder (e.g. `./resume/` or `./resumes/`):
```text
project/
├── resume/
│   ├── candidate_01.pdf
│   ├── candidate_02.pdf
│   ├── candidate_03.pdf
│   └── ...
```

### Output: Ranked JSON (`./output/results.json`)
The batch processor outputs a structured array of evaluated candidates:

```json
[
  {
    "rank": 1,
    "candidate_name": "Kartikay Sinha",
    "file_name": "candidate_01.pdf",
    "eligible": true,
    "total_score": 86,
    "score_breakdown": {
      "ai_project_depth": 36,
      "python_backend": 26,
      "cloud_fullstack": 12,
      "github": 8,
      "engineering_depth": 4
    },
    "matched_skills": [
      "Python",
      "FastAPI",
      "LangGraph",
      "LlamaIndex",
      "PostgreSQL",
      "Redis",
      "Docker",
      "GCP"
    ],
    "project_summary": "Multi-agent RAG system using LangGraph and LlamaIndex for financial document analysis with tool calling and ChromaDB.",
    "github_summary": "Active GitHub profile with recent contributions and maintained Python repositories.",
    "github_enrichment_status": "success",
    "strengths": [
      "Strong practical experience with LangGraph and multi-agent orchestration.",
      "Solid Python backend foundation using FastAPI, Redis, and PostgreSQL.",
      "Demonstrated engineering depth with caching, task queues, and unit testing."
    ],
    "concerns": [
      "Could gain more experience with cloud-native observability tools (Prometheus/Grafana)."
    ]
  },
  {
    "rank": null,
    "candidate_name": "John Doe",
    "file_name": "candidate_02.pdf",
    "eligible": false,
    "rejection_reasons": [
      "No evidence of Python stack (JavaScript/React only profile)",
      "No AI/agentic project evidence"
    ],
    "total_score": 0,
    "score_breakdown": {
      "ai_project_depth": 0,
      "python_backend": 0,
      "cloud_fullstack": 0,
      "github": 0,
      "engineering_depth": 0
    },
    "matched_skills": ["React", "Node.js", "Express"],
    "project_summary": "Standard web applications without Python or AI implementation.",
    "github_summary": "Not evaluated due to ineligibility.",
    "github_enrichment_status": "not_available",
    "strengths": [],
    "concerns": ["Candidate does not meet minimum eligibility criteria."]
  }
]
```

### Terminal Batch Summary
Upon completion, `main.py` prints the required summary metrics directly in the console:

```text
================================================================================
📊 BATCH SCREENING & RANKING SUMMARY
================================================================================
📁 Total Resumes Found:        10
✅ Successfully Evaluated:     10
🎯 Eligible Candidates:       7
❌ Ineligible / Rejected:      3
⚠️  Failed / Unreadable:        0
================================================================================

🏆 TOP RANKED CANDIDATES SHORTLIST:
Rank  Score   Candidate Name              Highlights
--------------------------------------------------------------------------------
#1    86      Kartikay Sinha              Python, FastAPI, LangGraph, PostgreSQL
#2    81      Priya Sharma                FastAPI, LlamaIndex, RAG, Docker
#3    78      Aman Verma                  LangChain, Vector Search, Redis, GCP
================================================================================
```

---

## 🎯 Scoring Rubric & Rules

### 1. Hard Eligibility Filter (Mandatory)
Candidates must satisfy **both** rules to be eligible for ranking:
1. **Python Evidence:** Python must appear as a genuine skill, project implementation language, or work technology. *A JavaScript/Java/React-only candidate is rejected.*
2. **AI / Agentic Evidence:** Must demonstrate at least one meaningful AI/LLM/RAG/agentic project (LangChain, LangGraph, LlamaIndex, RAG retrieval pipelines, embeddings/vector search, tool-calling agents, or multi-agent workflows).

*Note: Ineligible candidates receive `eligible: false`, `total_score: 0`, and explicit `rejection_reasons`.*

### 2. 100-Point Candidate Ranking (Eligible Only)

| Category | Weight | What is Evaluated & Rewarded |
| :--- | :---: | :--- |
| **AI / Agentic / RAG Project Depth** | **40** | Multi-agent workflows, state management, tool calling, RAG pipelines, retrieval & embeddings, evaluation pipelines, real user impact. *(5–15 point penalty for thin API wrappers).* |
| **Python & Backend Engineering** | **30** | Python idioms, FastAPI, async programming (`asyncio`), PostgreSQL schema design, Redis caching. Project evidence weighted over skill lists. |
| **Cloud / Deployment / Full Stack** | **15** | GCP/AWS, Docker containerization, cloud deployment, and full-stack React/Next.js when part of an end-to-end system. |
| **GitHub Activity** | **10** | Recent engineering activity (0–5 pts) + maintained/relevant repositories (0–5 pts). *Missing GitHub does not disqualify.* |
| **Engineering Depth Signals** | **5** | Unit testing (`pytest`), architectural modularity, caching, message queues, observability, retries, and concurrency. |

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Python 3.11 and 3.12)
- Virtual environment recommended

### 1. Clone & Install Dependencies
```bash
# Clone the repository
git clone <your-repo-url>
cd hiring-agent-test

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file from the example:
```bash
cp .env.example .env
```
Add your credentials to `.env`:
```env
# LLM Provider Configuration
LLM_PROVIDER=gemini
DEFAULT_MODEL=gemini-2.5-flash
GEMINI_API_KEY=AIzaSyYourActualKeyHere

# Optional: GitHub token to avoid public API rate limits (5,000 requests/hr vs 60/hr)
GITHUB_TOKEN=ghp_YourGitHubTokenHere
```

---

## 💻 How to Run

### 1. Batch Screening & Ranking (All Resumes)
To process an entire directory of resumes and generate the ranked shortlist:
```bash
python main.py --input ./resume --output ./output/results.json --role software_engineering_intern
```

**CLI Flags:**
- `--input` / `-i`: Path to the folder containing PDF resumes (default: `./resume`).
- `--output` / `-o`: Destination path for the output JSON (default: `./output/results.json`).
- `--role` / `-r`: Job role to evaluate against (default: `software_engineering_intern`).

### 2. Single Resume Evaluation
To inspect a single candidate in detail:
```bash
python score.py ./resume/candidate_01.pdf --role software_engineering_intern
```

---

## 🧠 Design Decisions

1. **Deterministic Eligibility Before Scoring:**  
   To prevent well-written resumes from overriding core job requirements, hard filters are applied prior to scoring. Non-Python or non-AI profiles are rejected deterministically with zero score and documented rejection reasons.

2. **Penalty for Thin API Wrappers:**  
   Many candidates claim AI experience from basic single-line LLM API calls. The rubric explicitly detects and deducts 5–15 points for "thin wrappers" that lack retrieval, state management, tool calling, data processing, or backend logic.

3. **Incremental Saving for Batch Resilience:**  
   `main.py` writes to the output file after every single candidate. If network issues, rate limits, or process interruptions occur during a 50-resume run, completed progress is preserved.

4. **Fault-Tolerant File Handling:**  
   Corrupted PDFs or missing fields do not crash the batch. Errors are isolated, recorded as `failed/unreadable` in the output record, and the batch continues seamlessly.

5. **Non-Disqualifying GitHub Signals:**  
   GitHub is treated as an additive signal (0–10 points). Missing profiles, private repositories, or rate-limited API calls never cause candidate ineligibility.

---

## 🔮 If I Had More Time

1. **Bounded Async Concurrency:**  
   Introduce an asynchronous worker queue (using `asyncio` and `aiohttp`) with a concurrency limit (e.g., 3–5 concurrent workers) to speed up 50+ resume batches from minutes to seconds.
2. **Multi-Format Ingestion (DOCX / TXT):**  
   Add native python-docx support to extract and score non-PDF resume formats seamlessly.
3. **RAG & Agent Evaluation Integration:**  
   Integrate automated evaluation tools like Ragas or TruLens to evaluate candidate project repositories directly against code quality benchmarks.
4. **Vector Deduplication:**  
   Add lightweight semantic hashing to detect duplicate candidate submissions or reused resume templates across large batches.

---

## 👏 Credits & Acknowledgements

- Core architecture and evaluation foundation cloned and adapted from HackerRank. Credits to [**@shlokashah**](https://github.com/shlokashah), software engineer at **HackerRank**.
- Extended with the SDE Intern + AI screening rubric, hard filter validation, project-quality penalty detection, and batch processing pipeline.
