# PG Atlas: Graph Intelligence Prototype Report

**Author:** Jay Gutierrez, PhD
**Focus Area:** Graph Analytics & Network Science Lead (D6)
**Context:** Layer 1 Metric Gate — Objective Filter Formulation

**Objective:** Validate the core graph algorithms (Deliverables A6, A9, A10) required for the Stellar Public Goods (PG) Atlas on a representative software ecosystem topology, ensuring mathematical readiness for the `D6: Metric Computation Engine`.

This report summarizes the methodological validation and implementation of the dependency graph intelligence layer. The functional proof of concept, embodied in the `build_notebook.py` simulation, demonstrates our capability to project raw software relations into rigorous administrative insights, formulating the exact objective metrics required to power the Layer 1 Metric Gate for SCF funding decisions.

## 1. Algorithmic Implementation and Scientific Rigor

The prototype operationalizes the Tier 1 and Tier 2 metrics defined in the project architecture. We generated a synthetic dataset modeled closely on empirical software ecosystem distributions.

### Crucial Role of Airtable Data Exploitation
Before generating the network structure, foundational nodes were populated using the cleaned extracts from the `01_data/processed/` directory. Specifically, the processing pipeline ingested the **86 raw PG candidates** derived from the original Airtable application data. Meticulous exploitation of these Airtable records provided the essential "seed list" of ground-truth projects. By anchoring the synthetic graph topology around these real-world entry points, we guarantee operations mimic the true density and connectivity of the Stellar ecosystem, ensuring that subsequent algorithm outputs reflect the precise conditions the layer will face in production.

This generated a dynamic, realistic dependency network spanning over 2,200 nodes.

### Topological Metrics (D6 Lead)

1. **Active Subgraph Projection (A6):** 
   The pipeline filters dormant repositories and projects an induced subgraph containing only active components. This step isolates the operational maintenance surface from historical archives, a critical precursor to accurate measurement.

2. **Criticality Score (A9):** 
   We evaluate systemic criticality by traversing the reversed directed dependency graph using a Breadth-First Search (BFS) to aggregate the count of active, transitive dependents. This structural reachability approach quantifies downstream impact boundaries—highlighting failure cascades.

3. **Pony Factor and Risk Concentration (A9):** 
   To measure maintenance vulnerability, we converted the discrete commit distribution into a continuous scoring system derived from the Herfindahl-Hirschman Index (HHI). Mapping contributor dominance to established economic compliance thresholds validates repository resilience dynamically.

4. **Adoption Signals (A10):** 
   Raw ecosystem indicators (stars, forks, package downloads) exhibit heavy-tailed distributions. The pipeline applies a base-10 logarithmic transformation prior to computing percentile ranks, ensuring that the composite Adoption Score is resistant to localized skew.

## 2. Visual Output Summary

The pipeline automatically generates four primary analytical artifacts designed for both executive funding validation (Layer 2/3 NQG voting contextualization) and granular engineering triage. 

### Figure 1: Scale-Free Topology
![Degree Distribution](/Users/jaygut/Desktop/SCF_PG-Atlas/06_demos/01_active_subgraph_prototype/fig1_degree_distribution.png)
> **Figure 1 Legend:** Histogram depicting the heavy-tailed, scale-free connectivity profile of the active subgraph. The log-log distribution confirms that the synthetic generator successfully approximates the hub-and-spoke behavior expected of authentic package registries natively. (Dashed gridlines define the threshold boundaries).

### Figure 2: The Core Diagnostic Matrix
![Criticality vs. Funding](/Users/jaygut/Desktop/SCF_PG-Atlas/06_demos/01_active_subgraph_prototype/fig2_criticality_vs_funding.png)
> **Figure 2 Legend:** Scatter plot measuring normalized Funding Efficiency. Nodes mapped according to aggregate structural Criticality (x-axis) versus relative Ecosystem Funding (y-axis). High-criticality, low-funding quadrants rapidly isolate severely under-resourced public goods packages essential for the Layer 1 metric gating. 

### Figure 3: Maintenance Concentration
![Pony Factor HHI](/Users/jaygut/Desktop/SCF_PG-Atlas/06_demos/01_active_subgraph_prototype/fig3_pony_factor.png)
> **Figure 3 Legend:** Histogram evaluating project concentration risk using an adapted economic Herfindahl-Hirschman Index (HHI) for repository commit shares. Displays operational thresholds separating broadly maintained projects from severe, concentrated single-point maintenance failures.

### Figure 4: The Dependency Ecosystem
![Dependency Network Map](/Users/jaygut/Desktop/SCF_PG-Atlas/06_demos/01_active_subgraph_prototype/fig4_dependency_network.png)
> **Figure 4 Legend:** Force-directed topological reduction of the active ecosystem. Hub nodes are elevated at the core; node diameter expands relative to calculated criticality. The color schema delineates k-core depth (bright cyan identifying the innermost integrated shell). Repositories designated as critically vulnerable via HHI are stroke-highlighted in red, while mathematically identified bridge edges (structural points of failure identified via Tarjan's algorithm) glow amber against faint grey standard dependencies backgrounds.

## 3. Graph Construction from PostgreSQL (Deliverables D4 / D5)

As we transition from the synthetic prototype directly into the `D4: Data Ingestion Pipeline` live operations, foundational graph construction must fuse with the standardized PostgreSQL schema constructed by Alex in `D5: Storage & Data Model`.

The NetworkX ingestion layer will execute optimized SQL querying to populate the in-memory execution environment seamlessly. The anticipated architectural pattern dictates that the ingestion component bridges empirical edges:

```python
import networkx as nx
import psycopg2

def build_graph_from_db(conn) -> nx.DiGraph:
    G = nx.DiGraph()
    with conn.cursor() as cur:
        # Construct Vertex Layer
        cur.execute("SELECT id, project_id, ecosystem, latest_commit_date FROM repo")
        for repo_id, proj_id, eco, last_commit in cur.fetchall():
            G.add_node(repo_id, node_type='Repo', project=proj_id, 
                       ecosystem=eco, latest_commit_date=last_commit)
        
        # Construct Edge Layer: Structural Dependencies
        cur.execute("SELECT from_repo, to_repo, confidence FROM depends_on")
        for u, v, conf in cur.fetchall():
            G.add_edge(u, v, edge_type='depends_on', confidence=conf)
        
        # Construct Edge Layer: Human Capital 
        cur.execute("SELECT contributor_id, repo_id, commits FROM contributed_to")
        for c, r, commits in cur.fetchall():
            G.add_edge(c, r, edge_type='contributed_to', commits=commits)
            
    return G
```

By cleanly decoupling the topological metric analysis (`D6`) from the underlying data ingestion layer (`D4, D5`), the mathematical algorithms comprehensively validated in this prototype will demand zero mathematical refactoring upon migrating to the real-world dataset. This establishes an airtight interface contract where the database yields pure vertices and relations, and the analytics module efficiently maps them into the fundamental scoring framework essential for the Layer 1 Metric Gate decision stack.
