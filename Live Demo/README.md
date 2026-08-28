# Criminal Network Analysis — Dashboard Guide

This is a walkthrough of the live dashboard, written for anyone opening the
demo link rather than the codebase — investigators, judges, or reviewers
who want to know what they're looking at.

## Live demo

**[Open the live dashboard ](https://ai-powered-criminal-network-analysis-system-7sagw7tdjmwjxtzvvj.streamlit.app/)**

## What this is

An interactive tool that turns raw case data (call records, financial
transactions, FIR complaints) into a single relationship map, then
surfaces the people and patterns worth an investigator's attention —
automatically, without manually cross-referencing spreadsheets.

The dataset behind this demo is synthetic (500 people, generated with a
few deliberately hidden "criminal rings"), so every result can be checked
against a known answer. See the **Detected communities** table for that
validation.

## Reading the dashboard, top to bottom

### 1. Summary metrics
Five numbers at a glance: how many people are in the case, how many
relationships connect them, how many distinct clusters ("communities")
were found, and two headline red flags — circular money flows and
multi-channel pairs.

### 2. Network graph
The core visualization. Each dot is a person; each line is a relationship
(a call, a transaction, or an FIR link between them).

- 🔴 **Red nodes** — the most influential people in the network, ranked by
  *betweenness centrality*. These are the connectors — remove them and the
  network tends to fall apart into disconnected pieces. Often the people
  worth investigating first.
- 🟠 **Orange nodes** — people connected to someone else by more than one
  channel (e.g. they've called each other *and* exchanged money *and* show
  up together in an FIR). Multiple independent channels between the same
  two people is a stronger signal than any one channel alone.
- 🔵 **Blue nodes** — everyone else.

Hover any node for its exact centrality scores and which cluster it
belongs to. Use the sidebar to filter by relationship type, require a
minimum interaction count, or show only the flagged nodes.

### 3. Key players table
The same ranking as the red nodes, in table form — sortable, and easier to
scan if you're building a shortlist of leads.

### 4. Suspicious patterns (tabs)
Four automatically detected pattern types:
- **Circular money flows** — A pays B, B pays C, C pays back to A. A
  classic money-laundering shape, found by tracing cycles in the
  transaction graph.
- **Multi-relation pairs** — the orange nodes from the graph, listed with
  which specific relationship types connect them.
- **Call activity spikes** — people whose call volume on a given day was a
  statistical outlier compared to their own normal pattern.
- **Transaction outliers** — unusually large payments, or payments made at
  odd hours (midnight–5am).

Each of these is a lead for a human to review, not a conclusion — the tool
surfaces the pattern, an investigator decides what it means.

### 5. Detected communities
The network broken into clusters of people who interact mostly with each
other. In this demo, each cluster is checked against the dataset's known
"ring" ground truth, so you can see directly how well the clustering
recovers the real groups.

### 6. Investigate a person
Pick anyone by name to see every underlying record involving them — their
calls, transactions, and FIR mentions — plus which flags apply to them.
This is the trace-back: nothing in the dashboard is a black-box score,
every flag can be clicked through to the exact records behind it.

## A note on what this is (and isn't)

This is a decision-support tool, not a decision-maker. Every score, flag,
and cluster is meant to focus investigator attention — none of it is
evidence on its own, and none of it should be treated as a determination
of guilt or involvement. All output should be reviewed against the
underlying records (which the dashboard makes one click away) before
acting on it.
