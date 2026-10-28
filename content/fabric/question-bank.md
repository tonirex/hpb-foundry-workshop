# Fabric question bank — Mei Lin's questions and Rahim's cohort question

LiveWell Coach calls Fabric for two reasons. Mei Lin (fictional HPB programme officer) asks exactly
**two** programme questions: one participant comparison and one optional specialist demonstration.
Rahim never asks Fabric about himself, but an optional operator demonstration asks **one** aggregate cohort question ("people in my age band")
to pick a programme he is likely to stick with. Every `fabric` beat in `content/narrative/rahim.md` points
at one of these ids, and every id has a prompt in `content/prompts/test-prompts.json`. Reference answers
are recomputed from the data by `scripts/validate-narrative.py` into `reference-answers.json` — never copy
numbers from a portal run.

| question_id | Question (verbatim) | prompt_id | Where it is used | Traversal | Live gate |
|---|---|---|---|---|---|
| `q_disengaged_regions` | Which regions have the highest share of disengaged residents? | `fabric_q_disengaged_regions` | [Lab 3 Fabric step](../labs/fabric-step.md) checkpoint | Resident —livesIn→ Region (filter `is_disengaged = 1`) | **strict** — exact counts, top region ±1 rank |
| `q_programmes_disengaged_enrolled` | Which programmes have the most disengaged residents enrolled? | `lab4_q_programmes_disengaged` | [Facilitator demonstrations](../admin/FACILITATOR-DEMOS.md#optional-fabric-extensions) | Resident (`is_disengaged = 1`) —enrolledIn→ Programme | **strict** — exact counts, top programme ±1 rank |

**Why would Mei ask Fabric here, and what does the coach do with the answer?** (the table-read test)

1. `q_disengaged_regions` — Mei is deciding where to run the next re-engagement roadshow. Only the
   governed Resident 360 knows who is disengaged; the coach returns the ranked regions and suggests
   pairing the top region with indoor, hazy-day-friendly activities from the activities catalogue.
2. `q_programmes_disengaged_enrolled` — Mei is reviewing which programme teams to brief first. The
   Programme-Insights specialist answers from Fabric; the coach turns it into a one-line brief per programme.

## Rahim's cohort question (citizen seat, aggregate only)

The coach sends this question to the Fabric IQ tool itself, after reading Rahim's profile. The only thing it
takes from the profile is his age band. It never sends his name, `resident_id`, planning area or any other
detail that narrows the group to one person. The prompt is Rahim's own words. The question below is what the
coach should send to Fabric, and it is the text the live layer asks the data agent.

| question_id | Question the coach sends to Fabric (verbatim) | prompt_id | Where it is used | Traversal | Live gate |
|---|---|---|---|---|---|
| `q_programme_fit` | For residents in age band 60-64, how many enrolled in each programme and how many dropped out? | `lab3_programme_fit` | [Facilitator demonstrations](../admin/FACILITATOR-DEMOS.md#optional-fabric-extensions) | Resident (`age_band`) —enrolledIn→ Programme, and —droppedOut→ Programme | **strict** — exact enrolled and dropped counts per programme (counts under 5 may show as "fewer than 5") |

**Why would the coach ask Fabric for Rahim, and what does it do with the answer?** Rahim dropped out of
Healthier SG. The guides tell him *what* helps with pre-diabetes. Only the governed Resident 360 knows
*which programmes people his age actually stay in*. The coach recommends the lowest drop-out programme he is not
already in, explains why it fits his profile, finds that programme's intake session with `find_activities`, and
asks before `register_interest`. Age band only: adding his screening risk shrinks the cohort to 20 people,
and then every drop-out count falls under the "fewer than 5" rule (ASSUMPTIONS.md 6.7).

## Canonical GQL (the graph check)

**Historical / graph-specific reference, not the current data-agent query contract.** Ontology context now
guides source-native SQL, KQL or DAX. These GQL examples remain for the separate graph check and old replay;
do not present them as what a current data agent must generate. See [current ontology context](https://learn.microsoft.com/fabric/data-science/data-agent-ontology-sources).

`scripts/validate-narrative.py --layers live` runs these queries directly on the ontology's graph model
(`GraphModels/{id}/executeQuery`, preview) and requires the reference answers exactly, before it asks the
data agent. If the graph check passes and the data agent does not, the data is right and the variance is
in that legacy agent's question-to-GQL step. A successful graph check does not validate the current source-native
data-agent runtime; inspect its selected source, query and output separately.

```gql name=q_disengaged_regions
MATCH (r:Resident)-[:livesIn]->(g:Region)
RETURN g.region AS region, count(r) AS residents, sum(r.is_disengaged) AS disengaged
GROUP BY region ORDER BY disengaged DESC
```

```gql name=q_dropped_attended_heldin
MATCH (r:Resident)-[:attended]->(o:EventOccurrence)-[:heldIn]->(g:Region)
WHERE r.programmes_dropped >= 1
RETURN g.region AS region, count(DISTINCT r.resident_id) AS residents
GROUP BY region ORDER BY residents DESC
```

```gql name=q_dropped_attended_heldin.distinct_residents
MATCH (r:Resident)-[:attended]->(o:EventOccurrence)
WHERE r.programmes_dropped >= 1
RETURN count(DISTINCT r.resident_id) AS residents
```

```gql name=q_programmes_disengaged_enrolled
MATCH (r:Resident)-[:enrolledIn]->(p:Programme)
WHERE r.is_disengaged = 1
RETURN p.programme_name AS programme_name, count(DISTINCT r.resident_id) AS disengaged_enrolled
GROUP BY programme_name ORDER BY disengaged_enrolled DESC
```

Rahim's cohort question walks `enrolledIn` for everyone who joined, then `droppedOut` for those who left.
Edges have no properties, so "dropped" has its own edge instead of a status on `enrolledIn`. `droppedOut` sits
in an `OPTIONAL MATCH`: putting both edges in one `MATCH` keeps only the residents who dropped out, so
"enrolled" would equal "dropped". The data agent does not write the `OPTIONAL MATCH` itself: given one
combined question, its NL-to-GQL step builds that single `MATCH`. So its agent instructions tell it to query
twice, `enrolledIn` per programme and then `droppedOut` per programme, and join the two tables (ASSUMPTIONS.md 6.7).
Percentages are worked out from the counts, not inside the query (Fabric GQL rejects inline arithmetic such
as `round(100.0 * … / …)`).

```gql name=q_programme_fit
MATCH (r:Resident)-[:enrolledIn]->(p:Programme)
WHERE r.age_band = '60-64'
OPTIONAL MATCH (r)-[d:droppedOut]->(p)
RETURN p.programme_name AS programme_name, count(DISTINCT r.resident_id) AS enrolled, count(d) AS dropped
GROUP BY programme_name ORDER BY enrolled DESC
```

The two disengaged questions also have ready-made counts on the entity nodes (gold aggregates built by
`scripts/r360.py`, like `Region.resident_count`). They return one row per group, so they stay well under
the data agent's 200-row query limit; the data source instructions point the agent at them first. The
graph check requires them to equal the traversal counts above.

```gql name=q_disengaged_regions.gold
MATCH (g:Region)
RETURN g.region AS region, g.disengaged_residents AS disengaged, g.resident_count AS residents,
       g.disengaged_share_pct AS share_pct
ORDER BY share_pct DESC
```

```gql name=q_programmes_disengaged_enrolled.gold
MATCH (p:Programme)
RETURN p.programme_name AS programme_name, p.disengaged_enrolled AS disengaged_enrolled
ORDER BY disengaged_enrolled DESC
```

## Exploration questions (not in the narrative; for facilitators and curious participants)

Aggregate-only, adapted from the Resident 360 kit question bank (MIT, see NOTICE.md). They are not gated.

- How many residents are disengaged by age band?
- Compare average daily steps for residents who attended at least one event vs those who attended none.
- How many residents attended events in each region where the events were held?
- Which hazy regions have the lowest average MVPA?
- Healthpoints earned by home region, highest first.

## Never ask the data agent

- Anything that names a resident or a `resident_id` (the coach's `fabric` block forbids it; the data agent
  also refuses).
- Citizen questions about one person or about health advice ("what should I eat?", "how am I doing?").
  Health advice goes to the Foundry IQ knowledge base, and the resident's own data comes from the profile
  tool. The only citizen-seat Fabric question is the aggregate cohort question above.
