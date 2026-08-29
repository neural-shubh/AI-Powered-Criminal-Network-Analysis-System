"""
AI-Powered Criminal Network Analysis — Streamlit Dashboard
Loads persons/calls/transactions/fir_text CSVs, builds a unified relationship
graph, runs centrality/community/anomaly analytics, and renders an
interactive network visualization with filters.

Run locally:
    streamlit run app.py
Deploy: push to GitHub, connect repo on Streamlit Community Cloud.
"""

import io
import pickle
from collections import Counter
from itertools import combinations

import networkx as nx
import pandas as pd
import streamlit as st
from networkx.algorithms.community import louvain_communities
from pyvis.network import Network
from rapidfuzz import process, fuzz

st.set_page_config(page_title="Criminal Network Analysis", layout="wide")

# ----------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------
st.sidebar.header("Data")
use_sample = st.sidebar.checkbox("Use uploaded sample files", value=True)

REQUIRED = ["persons.csv", "calls.csv", "transactions.csv", "fir_text.csv"]


@st.cache_data(show_spinner=False)
def load_default():
    """Looks for CSVs sitting next to app.py. Returns None if missing."""
    dfs = {}
    for name in REQUIRED:
        try:
            dfs[name] = pd.read_csv(name)
        except FileNotFoundError:
            return None
    return dfs


def load_uploaded(files):
    dfs = {}
    for f in files:
        dfs[f.name] = pd.read_csv(f)
    return dfs


dfs = None
if use_sample:
    dfs = load_default()

if dfs is None:
    st.sidebar.info("Upload persons.csv, calls.csv, transactions.csv, fir_text.csv")
    uploaded = st.sidebar.file_uploader(
        "CSV files", type="csv", accept_multiple_files=True
    )
    if uploaded:
        dfs = load_uploaded(uploaded)

if dfs is None or not all(name in dfs for name in REQUIRED):
    st.title("Criminal Network Analysis")
    st.warning(
        "Waiting for data. Place persons.csv, calls.csv, transactions.csv, "
        "fir_text.csv next to app.py, or upload them in the sidebar."
    )
    st.stop()

persons = dfs["persons.csv"]
calls = dfs["calls.csv"].copy()
txns = dfs["transactions.csv"].copy()
firs = dfs["fir_text.csv"]

calls["start_time"] = pd.to_datetime(calls["start_time"])
txns["txn_time"] = pd.to_datetime(txns["txn_time"])

# ----------------------------------------------------------------------
# Graph construction (mirrors the Colab pipeline)
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_edges(calls, txns, firs):
    call_edges = calls.rename(
        columns={"caller_id": "source", "callee_id": "target", "start_time": "timestamp"}
    )
    call_edges["relation_type"] = "call"
    call_edges["weight"] = call_edges["duration_sec"]
    call_edges["record_id"] = call_edges["call_id"]

    txn_edges = txns.rename(
        columns={"sender_id": "source", "receiver_id": "target", "txn_time": "timestamp"}
    )
    txn_edges["relation_type"] = "transaction"
    txn_edges["weight"] = txn_edges["amount_inr"]
    txn_edges["record_id"] = txn_edges["txn_id"]

    fir_edges = firs.rename(
        columns={"complainant_id": "source", "accused_id": "target", "date": "timestamp"}
    )
    fir_edges["relation_type"] = "fir_complaint"
    fir_edges["weight"] = 1
    fir_edges["record_id"] = fir_edges["fir_id"]

    cols = ["source", "target", "relation_type", "weight", "timestamp", "record_id"]
    return pd.concat([call_edges[cols], txn_edges[cols], fir_edges[cols]], ignore_index=True)


@st.cache_resource(show_spinner=False)
def build_graph(all_edges_json, persons_json):
    all_edges = pd.read_json(io.StringIO(all_edges_json))
    persons_df = pd.read_json(io.StringIO(persons_json))

    G_simple = nx.Graph()
    for _, p in persons_df.iterrows():
        G_simple.add_node(
            p["person_id"],
            name=p["name"],
            city=p.get("city", ""),
            state=p.get("state", ""),
            ring_id=p.get("ring_id") if pd.notna(p.get("ring_id")) and p.get("ring_id") != "" else None,
        )

    edge_info = {}
    for _, e in all_edges.iterrows():
        key = tuple(sorted((e["source"], e["target"])))
        edge_info.setdefault(key, {"count": 0, "relations": set(), "records": {}})
        edge_info[key]["count"] += 1
        edge_info[key]["relations"].add(e["relation_type"])
        edge_info[key]["records"].setdefault(e["relation_type"], []).append(e["record_id"])

    for (u, v), info in edge_info.items():
        if u in G_simple and v in G_simple:
            G_simple.add_edge(u, v, weight=info["count"], relations=list(info["relations"]),
                               records=info["records"])

    return G_simple


all_edges = build_edges(calls, txns, firs)
G = build_graph(all_edges.to_json(), persons.to_json())

# ----------------------------------------------------------------------
# Analytics (cached on the node/edge count as a cheap invalidation key)
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def compute_centrality(_G, cache_key):
    degree = nx.degree_centrality(_G)
    betweenness = nx.betweenness_centrality(_G, weight="weight")
    pagerank = nx.pagerank(_G, weight="weight")
    return degree, betweenness, pagerank


@st.cache_data(show_spinner=False)
def compute_communities(_G, cache_key):
    return louvain_communities(_G, weight="weight", seed=42)


cache_key = f"{G.number_of_nodes()}-{G.number_of_edges()}"
degree_cent, betweenness, pagerank = compute_centrality(G, cache_key)
communities = compute_communities(G, cache_key)

node_to_community = {}
for i, comm in enumerate(communities):
    for n in comm:
        node_to_community[n] = i


# ----------------------------------------------------------------------
# Anomaly detection
# ----------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def detect_call_spikes(calls_df, z_thresh=2.5):
    records = []
    for pid in pd.concat([calls_df["caller_id"], calls_df["callee_id"]]).unique():
        person_calls = calls_df[(calls_df["caller_id"] == pid) | (calls_df["callee_id"] == pid)]
        if len(person_calls) < 3:
            continue
        daily = person_calls.set_index("start_time").resample("D").size()
        if daily.std() == 0 or len(daily) < 2:
            continue
        z = (daily - daily.mean()) / daily.std()
        for date, val in z[z > z_thresh].items():
            records.append({"person_id": pid, "date": date, "z_score": round(val, 2)})
    return pd.DataFrame(records)


@st.cache_data(show_spinner=False)
def detect_circular_flows(txns_df, max_cycle_len=4):
    edge_map = {}
    for _, t in txns_df.iterrows():
        key = (t["sender_id"], t["receiver_id"])
        edge_map.setdefault(key, {"amount": 0.0, "txn_ids": []})
        edge_map[key]["amount"] += t["amount_inr"]
        edge_map[key]["txn_ids"].append(t["txn_id"])

    Gt = nx.DiGraph()
    for (u, v), info in edge_map.items():
        Gt.add_edge(u, v, amount=info["amount"], txn_ids=info["txn_ids"])

    def collect(cycle):
        total, txn_ids = 0.0, []
        for i in range(len(cycle)):
            edge_data = Gt[cycle[i]][cycle[(i + 1) % len(cycle)]]
            total += edge_data["amount"]
            txn_ids += edge_data["txn_ids"]
        return {
            "cycle": " -> ".join(map(str, cycle)) + f" -> {cycle[0]}",
            "length": len(cycle),
            "total_amount": round(total, 2),
            "txn_ids": ", ".join(map(str, txn_ids)),
        }

    cycles = []
    try:
        for cycle in nx.simple_cycles(Gt, length_bound=max_cycle_len):
            cycles.append(collect(cycle))
    except TypeError:
        # older networkx without length_bound
        for cycle in nx.simple_cycles(Gt):
            if len(cycle) <= max_cycle_len:
                cycles.append(collect(cycle))
    return pd.DataFrame(cycles).sort_values("total_amount", ascending=False) if cycles else pd.DataFrame()


@st.cache_data(show_spinner=False)
def detect_txn_outliers(txns_df, z_thresh=3.0, odd_hours=(0, 5)):
    out = txns_df.copy()
    z = (out["amount_inr"] - out["amount_inr"].mean()) / out["amount_inr"].std()
    out["amount_z"] = z.round(2)
    out["is_odd_hour"] = out["txn_time"].dt.hour.between(*odd_hours)
    return out[(out["amount_z"].abs() > z_thresh) | out["is_odd_hour"]][
        ["txn_id", "sender_id", "receiver_id", "amount_inr", "txn_time", "amount_z", "is_odd_hour"]
    ]


def multi_relation_pairs(_G):
    flags = []
    for u, v, data in _G.edges(data=True):
        if len(data.get("relations", [])) > 1:
            records = data.get("records", {})
            source_str = "; ".join(f"{rel}: {ids}" for rel, ids in records.items())
            flags.append({
                "person_a": _G.nodes[u].get("name", u),
                "person_b": _G.nodes[v].get("name", v),
                "relations": ", ".join(data["relations"]),
                "weight": data["weight"],
                "source_records": source_str,
            })
    return pd.DataFrame(flags).sort_values("weight", ascending=False) if flags else pd.DataFrame()


call_spikes = detect_call_spikes(calls)
circular_flows = detect_circular_flows(txns)
txn_outliers = detect_txn_outliers(txns)
multi_rel = multi_relation_pairs(G)

# ----------------------------------------------------------------------
# Sidebar filters
# ----------------------------------------------------------------------
st.sidebar.header("Graph filters")
relation_options = sorted({r for _, _, d in G.edges(data=True) for r in d.get("relations", [])})
selected_relations = st.sidebar.multiselect("Relation types", relation_options, default=relation_options)

min_weight = st.sidebar.slider("Minimum edge weight (interaction count)", 1, 10, 1)

top_n = st.sidebar.slider("Highlight top-N influencers", 5, 50, 10)

show_only_flagged = st.sidebar.checkbox("Show only flagged/multi-relation nodes", value=False)

# ----------------------------------------------------------------------
# Header + KPIs
# ----------------------------------------------------------------------
st.title("AI-Powered Criminal Network Analysis")
st.caption("Entity graph built from calls, transactions, and FIR complaint records.")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Persons", G.number_of_nodes())
k2.metric("Relationships", G.number_of_edges())
k3.metric("Communities detected", len(communities))
k4.metric("Circular money flows", len(circular_flows))
k5.metric("Multi-relation pairs", len(multi_rel))

# ----------------------------------------------------------------------
# Network visualization
# ----------------------------------------------------------------------
st.subheader("Network graph")

top_broker_ids = {pid for pid, _ in sorted(betweenness.items(), key=lambda x: -x[1])[:top_n]}
multi_rel_ids = set()
for u, v, data in G.edges(data=True):
    if len(data.get("relations", [])) > 1:
        multi_rel_ids.add(u)
        multi_rel_ids.add(v)

net = Network(height="650px", width="100%", bgcolor="#111111", font_color="white", notebook=False)
net.barnes_hut()

drawn_nodes = set()
for u, v, data in G.edges(data=True):
    rel = data.get("relations", [])
    if not any(r in selected_relations for r in rel):
        continue
    if data.get("weight", 0) < min_weight:
        continue
    if show_only_flagged and u not in multi_rel_ids and v not in multi_rel_ids:
        continue

    for n in (u, v):
        if n not in drawn_nodes:
            info = G.nodes[n]
            is_broker = n in top_broker_ids
            color = "#e74c3c" if is_broker else ("#f39c12" if n in multi_rel_ids else "#3498db")
            size = 15 + betweenness.get(n, 0) * 300
            title = (
                f"{info.get('name', n)}<br>City: {info.get('city', '-')}"
                f"<br>Betweenness: {betweenness.get(n, 0):.4f}"
                f"<br>PageRank: {pagerank.get(n, 0):.4f}"
                f"<br>Community: {node_to_community.get(n, '-')}"
            )
            net.add_node(n, label=info.get("name", str(n)), title=title, color=color, size=size)
            drawn_nodes.add(n)

    net.add_edge(u, v, value=data.get("weight", 1), title=", ".join(rel))

net.set_options("""
{
  "physics": {"stabilization": {"iterations": 150}},
  "edges": {"smooth": false}
}
""")

html_path = "/tmp/network.html"
net.save_graph(html_path)
with open(html_path, "r", encoding="utf-8") as f:
    st.components.v1.html(f.read(), height=670, scrolling=True)

st.caption(
    "🔴 Top-N influencers (betweenness centrality) · 🟠 Multi-relation pairs "
    "(connected by more than one channel) · 🔵 Other persons"
)

# ----------------------------------------------------------------------
# Key players table
# ----------------------------------------------------------------------
st.subheader("Key players")
players_df = pd.DataFrame({
    "person_id": list(G.nodes()),
    "name": [G.nodes[n].get("name", n) for n in G.nodes()],
    "degree_centrality": [round(degree_cent.get(n, 0), 4) for n in G.nodes()],
    "betweenness": [round(betweenness.get(n, 0), 4) for n in G.nodes()],
    "pagerank": [round(pagerank.get(n, 0), 4) for n in G.nodes()],
    "community": [node_to_community.get(n, -1) for n in G.nodes()],
})
st.dataframe(
    players_df.sort_values("betweenness", ascending=False).head(top_n),
    use_container_width=True,
)

# ----------------------------------------------------------------------
# Anomaly detection panels
# ----------------------------------------------------------------------
st.subheader("Suspicious patterns")
tab1, tab2, tab3, tab4 = st.tabs(
    ["Circular money flows", "Multi-relation pairs", "Call activity spikes", "Transaction outliers"]
)

with tab1:
    if len(circular_flows):
        st.dataframe(circular_flows, use_container_width=True)
    else:
        st.info("No circular transaction cycles detected in the current dataset.")

with tab2:
    if len(multi_rel):
        st.dataframe(multi_rel, use_container_width=True)
    else:
        st.info("No pairs connected by more than one relation type.")

with tab3:
    if len(call_spikes):
        st.dataframe(call_spikes.sort_values("z_score", ascending=False), use_container_width=True)
    else:
        st.info("No statistically significant call spikes detected.")

with tab4:
    if len(txn_outliers):
        st.dataframe(txn_outliers, use_container_width=True)
    else:
        st.info("No transaction outliers detected.")

# ----------------------------------------------------------------------
# Community / ring breakdown
# ----------------------------------------------------------------------
st.subheader("Detected communities")
comm_rows = []
for i, comm in enumerate(communities):
    ring_ids = [G.nodes[n]["ring_id"] for n in comm if G.nodes[n].get("ring_id") is not None]
    dominant_ring = Counter(ring_ids).most_common(1)[0] if ring_ids else ("-", 0)
    comm_rows.append({
        "community_id": i,
        "size": len(comm),
        "dominant_ring_id": dominant_ring[0],
        "members_in_dominant_ring": dominant_ring[1],
        "members": ", ".join(str(G.nodes[n].get("name", n)) for n in list(comm)[:8])
                   + (" ..." if len(comm) > 8 else ""),
    })
st.dataframe(pd.DataFrame(comm_rows).sort_values("size", ascending=False), use_container_width=True)

# ----------------------------------------------------------------------
# Explainability: search-by-name trace-back
# ----------------------------------------------------------------------
st.subheader("Search a person")
st.caption("Search by name. Every result traces back to the underlying call, transaction, and FIR records.")

name_to_id = {G.nodes[n].get("name", str(n)): n for n in G.nodes()}
all_names = list(name_to_id.keys())

search_query = st.text_input("Enter a name", "", placeholder="e.g. Rakesh Kumar")

selected_name, selected_id, match_score = None, None, None

if search_query.strip():
    exact = [n for n in all_names if n.lower() == search_query.strip().lower()]
    if exact:
        selected_name, match_score = exact[0], 100
    else:
        match = process.extractOne(search_query, all_names, scorer=fuzz.WRatio, score_cutoff=70)
        if match:
            selected_name, match_score = match[0], match[1]

    if selected_name:
        selected_id = name_to_id[selected_name]
    else:
        st.warning(f'No record found for "{search_query}".')

if selected_id is not None:
    if match_score is not None and match_score < 100:
        st.caption(f'Closest match: **{selected_name}** ({match_score:.0f}% match to "{search_query}")')

    person_flags = []
    if selected_id in betweenness:
        person_flags.append(f"betweenness rank: {sorted(betweenness, key=betweenness.get, reverse=True).index(selected_id) + 1} of {len(betweenness)}")
    if len(multi_rel):
        if (multi_rel["person_a"] == selected_name).any() or (multi_rel["person_b"] == selected_name).any():
            person_flags.append("involved in a multi-relation pair")
    if len(call_spikes) and selected_id in call_spikes["person_id"].values:
        person_flags.append("flagged for a call activity spike")
    if person_flags:
        st.markdown("**Flags:** " + " · ".join(person_flags))

    evid_calls = calls[(calls["caller_id"] == selected_id) | (calls["callee_id"] == selected_id)]
    evid_txns = txns[(txns["sender_id"] == selected_id) | (txns["receiver_id"] == selected_id)]
    evid_firs = firs[(firs["complainant_id"] == selected_id) | (firs["accused_id"] == selected_id)]

    ec1, ec2, ec3 = st.columns(3)
    ec1.metric("Calls", len(evid_calls))
    ec2.metric("Transactions", len(evid_txns))
    ec3.metric("FIR mentions", len(evid_firs))

    with st.expander(f"Source records for {selected_name}", expanded=False):
        st.markdown("**Calls**")
        st.dataframe(evid_calls, use_container_width=True) if len(evid_calls) else st.caption("None.")
        st.markdown("**Transactions**")
        st.dataframe(evid_txns, use_container_width=True) if len(evid_txns) else st.caption("None.")
        st.markdown("**FIR complaints**")
        st.dataframe(evid_firs[["fir_id", "date", "complainant_id", "accused_id", "narrative"]], use_container_width=True) if len(evid_firs) else st.caption("None.")
elif not search_query.strip():
    st.caption("Type a name above to search the case database.")

# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------
st.sidebar.header("Export")
if st.sidebar.button("Save graph as .gpickle"):
    with open("/tmp/criminal_network.gpickle", "wb") as f:
        pickle.dump(G, f)
    with open("/tmp/criminal_network.gpickle", "rb") as f:
        st.sidebar.download_button("Download graph", f, file_name="criminal_network.gpickle")
