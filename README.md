# AI-Powered Criminal Network Analysis

An AI-powered system that analyzes structured and unstructured crime-related
data (FIRs, call detail records, financial transactions) to uncover hidden
criminal networks, identify key influencers, detect suspicious patterns, and
generate actionable intelligence for investigators.

Built for an SIH-style problem statement: *"Develop an AI-powered system that
automatically analyzes structured and unstructured crime-related data to
uncover criminal networks, identify key influencers, detect suspicious
patterns, and provide actionable intelligence for investigators."*

## Live demo

`[add your Streamlit Community Cloud link here after deploying]`

## Architecture

```
Data sources (FIR, CDR, transactions)
        │
        ▼
NLP extraction (regex + spaCy NER)
        │
        ▼
Graph construction (weighted NetworkX graph)
        │
        ▼
Analytics & anomaly detection (centrality, communities, cycles)
        │
        ▼
Streamlit dashboard (interactive graph & alerts)
```

1. **Data sources** — FIRs, call detail records (CDRs), and financial
   transaction logs. This repo ships a synthetic dataset (see
   [`generate_synthetic.py`](generate_synthetic.py)) with deliberately
   planted "criminal rings" used as ground truth for validation.
2. **NLP extraction** — a regex parser tuned to the FIR narrative template,
   with spaCy NER (`en_core_web_trf`) as a fallback/enrichment layer for
   less structured text.
3. **Graph construction** — calls, transactions, and FIR complaints are
   merged into a single weighted, multi-relational graph in NetworkX, with
   each person as a node and each interaction type (`call`, `transaction`,
   `fir_complaint`) as a typed edge.
4. **Analytics & anomaly detection**
   - Key player identification via degree, betweenness, and PageRank
     centrality
   - Community detection (Louvain), validated against the synthetic
     ground-truth rings
   - Circular money-flow detection (cycle finding on the transaction
     subgraph — a money-laundering signature)
   - Call activity spikes and burner-phone patterns
   - High-value / odd-hour transaction outliers
   - Multi-relation pair flagging (people connected by more than one
     channel — a strong investigative lead)
5. **Dashboard** — a Streamlit app with an interactive network graph,
   filters by relation type and interaction strength, a key-players table,
   and tabs for each anomaly category.

## Project structure

```
.
├── app.py                    # Streamlit dashboard
├── requirements.txt          # Python dependencies
├── generate_synthetic.py     # Synthetic dataset generator
├── persons.csv
├── calls.csv
├── transactions.csv
├── fir_text.csv
├── locations.csv
└── notebooks/
    └── AI_Powered_Criminal_Network_Analysis.ipynb   # Full analysis pipeline
```

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app looks for the four CSVs (`persons.csv`, `calls.csv`,
`transactions.csv`, `fir_text.csv`) next to `app.py` by default, or you can
upload them from the sidebar.

## Relationship extraction

Two extraction paths feed the graph:

- **Structured joins** — calls, transactions, and FIRs already carry
  sender/receiver IDs, so these become edges directly. This is the most
  reliable path and covers the bulk of the graph.
- **Text-derived relations** — a dependency-parsing extractor walks each
  sentence's subject–verb–object structure (e.g. "X called Y", "X
  transferred cash to Y") against a small crime-relation verb vocabulary,
  resolves the extracted names back to `person_id` via fuzzy matching, and
  attaches a confidence score per edge. This is the path that would
  generalize to real, unstructured surveillance/social-media text where no
  structured ID join exists.

Text-derived edges are tagged `relation_type = "text_extracted:<relation>"`
in the graph and carry a `min_confidence` value, so they can be filtered
out or down-weighted independently of the structured-source edges.

**Evaluation methodology**: extraction precision/recall is measured against
a synthetic "surveillance notes" test set with known ground-truth name
pairs (see the notebook). Precision = correctly extracted pairs / all
extracted pairs; recall = correctly extracted pairs / all true pairs.

| Metric | Value |
|---|---|
| Precision | `[fill in after running the eval cell]` |
| Recall | `[fill in after running the eval cell]` |

This number is measured against synthetic templates the extractor was
tuned against, so it's a validity check on the pipeline rather than
evidence of real-world performance on unanticipated phrasing.

## Explainability

Every flagged pattern in the dashboard traces back to source records:

- Circular money-flow cycles list the exact `txn_id`s that make up the loop.
- Multi-relation pairs list which `call_id`/`txn_id`/`fir_id` records back
  each relation type between the two people.
- The "Investigate a person" panel shows every call, transaction, and FIR
  mention involving a selected person, plus which analytical flags apply
  to them — so a lead is never just a score, it's traceable to evidence.

## Results on the synthetic dataset

| Metric | Value |
|---|---|
| Persons (nodes) | 500 |
| Relationships (edges) | 3,757 |
| Communities detected | 8 |
| Multi-relation pairs flagged | 22 |
| Circular money-flow cycles found | 29 |

Community detection was cross-checked against the dataset's planted
`ring_id` ground truth — detected communities show strong overlap with the
known rings (see the "Detected communities" table in the dashboard for the
per-community breakdown).

## Design notes / known limitations

- The synthetic FIR narratives follow a fixed template, so the current NLP
  layer leans on a tuned regex parser for reliability, with spaCy NER as a
  fallback for less structured text. On real, free-form reports the system
  would depend more heavily on the NER + relation-extraction layer.
- Relationships from calls and transactions come from structured ID joins
  already present in the source data, rather than being inferred from text
  — this keeps the graph accurate for this dataset, but a production system
  ingesting only unstructured reports would need dependency-parsing-based
  relation extraction to fill that gap.
- This is a demo/prototype: it has no access control, audit logging, or
  chain-of-custody tracking, which a real investigative tool would require.
- All output is intended as investigative leads for human review, not
  automated determinations.

## Tech stack

Python, pandas, spaCy, NetworkX, Streamlit, pyvis.
