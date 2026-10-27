# Climate-Aware, Honesty-Constrained Shade Placement for Mass Outdoor Events: The Design and Defense of the U-Shade System

*A systems and engineering paper documenting the architecture, methods, and design rationale of the U-Shade (HeatGuard / FestCOOL) festival shade-layout generator.*

---

## Abstract

Outdoor music festivals concentrate tens of thousands of people onto unshaded post-industrial ground during the hottest hours of the summer, yet the decision of *where* to put shade is still made by intuition. This paper documents U-Shade, a climate-aware decision-support system that places shade on the cells of a festival site that are simultaneously the hottest and the busiest, and that does so under an unusually strict epistemic discipline: every quantity the system reports carries an explicit provenance tier, no number is tuned after the fact to make a result pass, and the generative language model is structurally barred from making any design decision. The system is a deterministic, sequential pipeline. A large language model parses a free-text brief into four operational fields and a theme classification, using schema-constrained structured output and a retry loop terminated on the model's `stop_reason` rather than on response text. A real urban-microclimate service (infrared.city) returns a Universal Thermal Climate Index (UTCI) heat grid resampled onto a six-metre master lattice. A pedestrian-dynamics engine (JuPedSim, Collision-Free Speed Model) migrates a persistent crowd across the site over a continuous daytime timeline, driven by the real festival schedule and by stage popularity grounded in Spotify monthly-listener counts. The product of crowd density and thermal excess above a 26 °C comfort threshold defines a demand field, over which a Maximal Covering Location Problem is solved both by a deterministic greedy heuristic and by an exact integer program that emits a verifiable optimality certificate. Shade material is chosen as the lowest-transport-carbon locally available reclaimed archetype, with cooling effectiveness scaled by one minus the membrane's solar transmissivity. A cooling-acceptance gate, governed by hash-locked thresholds that fail at run time if edited, certifies that the layout actually cools. This paper describes each subsystem in full, defends the principal design decisions against their alternatives, and is candid about the system's boundaries: the crowd-density validation currently fails its Fruin ceiling and is therefore labelled assumed, the crowd-to-heat metabolic feedback is realized only in the visualization layer, and the live pipeline deliberately terminates at ranked shade zones, handing form-making to a human architect.

**摘要（繁體中文）**

大型戶外音樂節在盛夏最炎熱的時段，把數萬人聚集到缺乏遮蔭的後工業場地上，但「遮蔭該放在哪裡」這個決策至今多半仍憑直覺。本文記錄 U-Shade：一套具氣候意識的決策支援系統，將遮蔭佈署於場地中「最熱且最擁擠」的網格單元，並在一套異常嚴格的知識誠實紀律下運作——系統回報的每一個數值都標註明確的來源層級，沒有任何數字在事後被調整以使結果「通過」，且生成式語言模型在結構上被禁止做出任何設計決策。系統是一條確定性的循序管線：語言模型以受綱要約束的結構化輸出，將自由文字簡報解析為四個操作欄位與一個主題分類，其重試迴圈以模型的 `stop_reason` 而非回應文字作為終止條件；真實的都市微氣候服務（infrared.city）回傳通用熱氣候指數（UTCI）熱網格，重新取樣至六公尺的主控晶格；行人動力學引擎（JuPedSim 無碰撞速度模型）依真實節目表與以 Spotify 每月聆聽數為依據的舞台人氣，使持續性人群在連續的白晝時間軸上跨場移動。人群密度與超過 26 °C 舒適閾值之熱量過剩的乘積定義出需求場，並以確定性貪婪啟發法與可驗證最佳性憑證的精確整數規劃，求解最大覆蓋選址問題。遮蔭材料選為在地可得、運輸碳最低的回收原型，其降溫效益以「一減去薄膜太陽穿透率」予以縮放。一道以雜湊鎖定、若被竄改即在執行期失敗的降溫驗收閘門，證明佈局確實降溫。本文完整描述各子系統，逐一辯護主要設計決策，並坦白系統邊界：人群密度驗證目前未通過 Fruin 上限故標註為「假定」、人群對熱的代謝回饋僅實現於視覺化層、且實際管線刻意終止於排序後的遮蔭分區，把造形交給人類建築師。

**Keywords:** outdoor thermal comfort; UTCI; festival design; pedestrian dynamics; maximal covering location problem; integer programming; reclaimed materials; transport carbon; large language models; structured output; provenance; decision support

---

## 1. Introduction

### 1.1 The problem

Heat is now the deadliest weather hazard in much of Europe, and mass outdoor gatherings sit at the intersection of three aggravating factors: large, dense, immobile crowds; hard, low-albedo ground that stores and re-radiates solar load; and event schedules that deliberately concentrate attendance during late-afternoon peak-heat hours. A festival organizer who wants to mitigate that risk faces a spatial allocation question — *which* parts of a multi-hectare site should be shaded, given a finite number of structures and a finite budget — that is rarely answered analytically. Shade, when it is provided at all, tends to be placed where it is convenient to install rather than where the combination of heat and human density makes it most protective.

U-Shade is a decision-support system built to answer that question rigorously. It takes a festival brief and a site boundary, crosses a real thermal-comfort field with a real crowd-density field, and produces a ranked set of shade zones placed exactly where the heat and the crowd coincide. It then identifies the lowest-carbon locally available reclaimed material with which to clad each structure, and certifies, through an explicit acceptance gate, that the resulting layout reduces felt temperature by a pre-declared margin over a pre-declared fraction of the at-risk crowd.

### 1.2 What makes the system distinctive

Many tools could draw shade on a map. Three commitments distinguish this one, and the bulk of this paper is a defense of them.

The first is the **strict separation of language understanding from design**. A large language model (LLM) is used, but only as a translator: it converts a chaotic natural-language brief into four typed fields and a theme label, and it is structurally prevented from emitting anything else. Every spatial and quantitative decision is made by deterministic, auditable algorithms. This is not a performance compromise; it is a correctness and accountability decision, examined in Sections 4 and 17.

The second is **honesty as an engineered property**, not a stylistic one. Every reported number is tagged with a provenance tier — grounded (real datasheet, standard, or measurement), derived (computed from grounded inputs), assumed (a reasoned estimate with no measurement), or declared/placeholder (an honest constant or a deliberate null). Acceptance thresholds are content-hashed and verified at run time, so that a post-hoc edit to make a borderline run pass fails loudly rather than silently. Coverage is measured against projected shadows, not footprints, so the system cannot flatter itself when the sun is off-zenith. These mechanisms are described throughout and consolidated in Section 15.

The third is **a regenerative material stance**: shade is to be built from waste the surrounding city already contains. Carbon is accounted for on a recycled cut-off basis — manufacturing emissions of a reclaimed object are treated as zero, and only the round-trip transport from source to site is counted — and the comparator that selects a material minimizes that transport carbon, never price. The material layer is paired with a sourcing platform that scrapes real reclaimed-stock listings, binds them to a frozen catalogue of archetypes by a purely deterministic rule engine, and routes each source to the site over real road networks.

### 1.3 Contributions

This paper makes the following contributions, all documentary and architectural rather than experimental:

1. A complete, decision-by-decision description of a deployed climate-aware shade-placement pipeline, from natural-language intake to a human-facing deliverable.
2. A defense of the maximal-covering formulation of shade placement, including the use of a deterministic greedy heuristic as a permanent lower-bound witness that cross-checks every exact integer-program solve.
3. A demonstration of provenance-tiered, tamper-evident honesty engineering applied end-to-end to a design tool, including a run-time threshold-integrity tripwire and a strict optimality-vocabulary firewall.
4. A transparent account of the system's boundaries and asymmetries — including a crowd-density validation that honestly fails, a thermal feedback realized only in visualization, and a deliberate hand-off to a human architect — offered as a model of how a design tool can state what it does *not* know.

### 1.4 Scope and structure

The system has been known successively as FestCOOL, HeatGuard, and U-Shade; this paper uses U-Shade for the product and HeatGuard for the engine where the distinction matters. Section 2 situates the work against the thermal-comfort, location-science, pedestrian-dynamics, and life-cycle-assessment literatures. Section 3 gives the architecture and the data-flow contract. Sections 4 through 14 document each subsystem in the order a run traverses them. Section 15 consolidates the honesty machinery that cross-cuts all of them. Sections 16 through 19 evaluate, discuss, bound, and conclude. Because the paper is intended to let a reader understand the system exactly, it quotes thresholds, constants, and file-level rationale directly, and it flags every place where the specification and the running code diverge.

---

## 2. Background and Related Work

### 2.1 Outdoor thermal comfort and the UTCI

The thermal state of a person outdoors is not captured by air temperature alone. It depends on the combination of air temperature, mean radiant temperature, wind speed, and humidity, integrated through human thermoregulation. The Universal Thermal Climate Index (UTCI) was developed precisely to express that combination as a single equivalent temperature, derived from an advanced multi-node thermophysiological model coupled to a state-of-the-art clothing model (Jendritzky, de Dear, & Havenith, 2012; Bröde et al., 2012). UTCI is expressed in degrees Celsius and partitioned into thermal-stress categories; the band from roughly 9 °C to 26 °C is "no thermal stress," above which moderate, strong, very strong, and extreme heat-stress categories follow. U-Shade adopts UTCI as its comfort field, takes 26 °C as the threshold below which a location is not worth shading, and uses the 32 °C category boundary as a visual "danger" line. The choice of UTCI over simpler indices (air temperature) or over mean-radiant-temperature-only metrics is deliberate and, as Section 5 records, was reinforced by domain-expert review: the system computes UTCI through a radiation-based service and does not claim to solve airflow, and it says so plainly rather than implying a computational-fluid-dynamics capability it does not have.

### 2.2 Anthropogenic and metabolic heat

A dense crowd is itself a heat source. A resting adult dissipates on the order of one metabolic unit, about 58.2 W m⁻² of body surface or roughly 100–105 W per person (ASHRAE Standard 55, 2023; ISO 7730, 2005), rising to several hundred watts during sustained physical activity such as dancing. At festival densities this is not negligible: a packed, active crowd can locally emit sensible heat of the same order of magnitude as midday solar load. Urban-climate models such as the Town Energy Balance (Masson, 2000), SUEWS (Järvi, Grimmond, & Christen, 2011), and LUCY (Allen, Lindberg, & Grimmond, 2011) incorporate anthropogenic heat as a flux term, and reviews of anthropogenic heat estimation (Sailor, 2011) formalize the accounting. U-Shade models a crowd-to-heat feedback in this spirit — sensible metabolic heat, crowd-blocked wind, and added humidity from perspiration — but, as Section 7 documents candidly, no published open-air study isolates a crowd-only temperature rise at the relevant densities, so the entire coupling is labelled assumed and, in the current build, is wired only into the visualization.

### 2.3 Facility location and the maximal covering problem

Deciding where to place a limited number of facilities so as to serve the most demand is the subject of location science. The Maximal Covering Location Problem (MCLP) of Church and ReVelle (1974) asks exactly the question U-Shade must answer: given demand distributed over space and a fixed number *K* of facilities, each covering the demand within some region, choose the *K* sites that cover the greatest total demand. The MCLP is NP-hard in general but, as the coverage objective is a monotone submodular set function, the greedy heuristic that repeatedly adds the site of greatest marginal coverage enjoys the classical worst-case guarantee of (1 − 1/e) ≈ 0.63 of optimal (Nemhauser, Wolsey, & Fisher, 1978). Its exact form is a binary integer program whose linear relaxation is frequently tight, so moderate instances solve to proven optimality quickly with a modern mixed-integer solver such as HiGHS (Huangfu & Hall, 2018). U-Shade implements both: a greedy default and an exact integer program, with the greedy solution retained as a lower-bound witness that the exact solve must never under-cover. Section 8 develops this.

### 2.4 Pedestrian dynamics

Predicting where a crowd will be requires a model of pedestrian motion. The empirical foundation is the fundamental diagram relating walking speed to local density, calibrated by Weidmann (1993) and others, in which speed falls as density rises toward a jam value. Operational pedestrian level-of-service standards descend from Fruin (1971), whose categories culminate in a crush regime above roughly five to six persons per square metre. Microscopic simulation has converged on a family of force-based and speed-based models; U-Shade uses the Collision-Free Speed Model (Tordeux, Chraibi, & Seyfried, 2016) as implemented in the open-source JuPedSim framework, in which agents follow scripted journeys at a density-limited speed and never overlap. An earlier U-Shade crowd engine used deep reinforcement learning (proximal policy optimization; Schulman et al., 2017) via Stable-Baselines3 (Raffin et al., 2021); Section 6 records why it was retired in favour of the scripted-journey model, and why it was archived rather than deleted.

### 2.5 Life-cycle assessment and reclaimed materials

Life-cycle assessment (ISO 14044, 2006) offers a "cut-off" allocation in which a recycled or reclaimed material enters its next life carrying none of the burden of its original manufacture; only the impacts of the new use cycle are counted. U-Shade adopts this stance literally: for a reclaimed object, manufacturing carbon is set to zero and only transport is counted, using the UK government's published greenhouse-gas conversion factor for an average-laden heavy goods vehicle, 0.09752 kg CO₂e per tonne-kilometre (DEFRA/DESNZ, 2024). Transport distance is computed over real road networks rather than as a straight-line approximation, because an underestimate of distance would understate carbon and overstate the environmental claim; the routing uses OSRM-style road routing (Luxen & Vetter, 2011). Section 9 and Section 10 develop the material model and the sourcing platform.

### 2.6 Language models as constrained parsers

Large language models are fluent natural-language interpreters but unreliable arithmetic and design agents. A growing engineering practice constrains them to structured output bound by a schema, and judges loop termination on explicit model signals rather than on generated text. U-Shade follows this practice strictly. Its parser uses schema-constrained structured output, sets temperature to zero, and terminates its retry loop on the model's `stop_reason` field, treating the iteration cap purely as a backstop. The model is given a closed output schema with additional properties forbidden, so that it is mechanically unable to emit a field outside the four it is permitted. Section 4 documents the implementation and its rationale.

---

## 3. System Architecture

### 3.1 A deterministic, sequential pipeline

The defining architectural property of U-Shade is that its data flow is strictly sequential and deterministic. No machine-learning component invents architecture; the learned and generative components are confined to the edges — parsing text at the front, and (in a deferred phase) rendering aesthetic texture at the back. Between them sits a chain of pure functions, each consuming the validated artifact of the previous stage and emitting a validated artifact of its own. The canonical pipeline is:

```
parsed_brief → utci_grid → crowd_grid → structure_zones →
  gh_response → material_selection → acceptance_verdict → render
```

This eight-stage chain is the project's resume manifest and dependency contract. The running system, however, deliberately executes only a prefix of it. The live full-run, orchestrated as a background task, executes three stages — climate, crowd, placement — and terminates at `structure_zones`, the ranked set of shade zones. The geometry, material, acceptance, and render stages remain in the contract and exist in the codebase, but the API no longer chains them, because the project's governing decision is that the engine proposes and a human architect commits. Section 12 and Section 14 explain this boundary; it is important to state at the outset, because a reader could otherwise assume the running product performs steps that it intentionally hands off.

### 3.2 The master lattice

Every spatial artifact in the system is expressed on one shared coordinate lattice, established by the climate stage and inherited unchanged by every downstream stage. The lattice has a cell size of 6.0 metres and is expressed in the projected coordinate system UTM zone 31N (EPSG:32631), whose units are metres. The 6-metre choice is a deliberate compromise, defended in Section 5: the native microclimate service resolves at roughly one metre, but a one-metre lattice over a multi-hectare festival site would exceed a hundred thousand cells and make the downstream sort and solve intractable, whereas six metres is both human-scale shade granularity and a typical structural bay. The lattice convention is fixed: row 0 is the south edge, column 0 is the west edge. The crowd grid and the placement demand field join to the heat grid on the integer `(row, column)` key — never by positional zipping, which would silently misalign grids of differing cell counts — and a duplicate key is treated as an error rather than reconciled.

### 3.3 The stack as specified and as built

The specification calls for a Node.js orchestrator, a Python machine-learning microservice, and a React/Vite/Mapbox frontend. The system as built diverges from this in a way worth recording honestly. There is a single Python backend, implemented with FastAPI, that hosts the entire run pipeline and all artifact endpoints. The "Node orchestrator" was never built as a server; the only Node/TypeScript code that runs is the LLM parser and a manifest writer, invoked through a thin command-line interface, with no HTTP server. Integration between the TypeScript parser and the Python backend is by file on disk — the parser writes a validated `parsed_brief.json` that the backend reads — rather than by remote procedure call. The frontend is a React 19 application built with Vite 7 and TanStack Start, rendering a single persistent Mapbox GL canvas with deck.gl overlays. The numerical stack is pinned deliberately: numpy is held at the 1.26 series rather than 2.x, because the live pedestrian engine (JuPedSim 1.2.1) is compatible with numpy 1.26, whereas the 1.4 series of that engine would force numpy 2.2 and regress a frozen density-clustering path. The mixed-integer solver is SciPy's `milp` interface to HiGHS, lazily imported so that the greedy default path carries no solver dependency.

The key inter-service facts are: FastAPI listens on port 8000; the frontend dev server listens on 5173 and proxies `/api` to the backend; cross-origin requests are restricted to the local frontend origins and to the GET and POST methods. The LLM parser runs as `claude-sonnet-4-6` by default with `claude-haiku-4-5` as an infrastructure-error fallback, through the `@anthropic-ai/sdk` TypeScript SDK; it is not the Python Anthropic SDK, and a separate, unrelated Python LLM helper used by a materials-classifier experiment must not be confused with it.

### 3.4 Artifacts, contracts, and validation

Each stage's output is governed by a JSON schema with additional properties forbidden, and validation runs *before* any artifact is written to disk. An invalid artifact never reaches storage; a stage that cannot produce a valid artifact records an honest failure rather than writing a partial result. This validate-then-write discipline, combined with content-hash caching keyed on the real inputs of each stage, gives the pipeline two properties that recur throughout this paper: results are reproducible to the byte under a fixed seed, and an expensive external call (the paid microclimate service) is never repeated when its inputs are unchanged.

### 3.5 The provenance tier system

Cross-cutting the whole architecture is a four-tier provenance vocabulary applied per field: **grounded** for a real datasheet, standard, or measurement; **derived** for a value computed from grounded inputs; **assumed** for a reasoned estimate with no measurement behind it; and **declared** or **placeholder** for an honest constant or a deliberate null. The tiers obey a weakest-input-wins rule: a derived quantity computed from an assumed input is itself assumed. This vocabulary is not decorative. It determines what the user-facing deliverable is permitted to claim, it is enforced by tests that forbid optimality language outside the one module entitled to it, and it is the reason the system can fail a validation and keep its integrity rather than quietly relabelling a failure as a success. Section 15 treats it as a subject in its own right.

---

## 4. The Brief-Parsing Layer: A Language Model Confined to Translation

### 4.1 Function and rationale

The first stage of the pipeline turns a festival organizer's free-text brief into structured variables. The decision to use a large language model here, and *only* here, follows from the observation that natural-language briefs are chaotic — they mix capacity, budget, date, aesthetic intent, logistics, and irrelevance in arbitrary order and phrasing — while everything downstream needs a small number of clean, typed values. The model's sole function is to act as an algorithmic translator from chaotic text to injectable code variables. It is explicitly barred from placing structures, choosing dimensions, generating structural geometry, or estimating budgets. The project's governing instruction states the principle without qualification: the LLM never designs; all design is the deterministic core. The defense of this decision is taken up in Section 17; here the concern is how the confinement is implemented.

### 4.2 The four fields and the theme classification

The model is asked to emit exactly four required semantic fields — `capacity` (a non-negative integer), `budget` (a non-negative integer), `date` (an ISO calendar date), and `theme` (a closed classification into one of `maritime`, `natural`, `industrial`, or `urban`) — plus two optional time fields, `festival_start` and `festival_end`, in 24-hour `HH:MM` form, extracted only if the brief states them. The contract schema additionally records a `schema_version`, but this is injected by the code as a constant after the model returns; the model is never asked for it. The theme is the only field that is a *classification* rather than an *extraction*: capacity, budget, and date must be present in the brief or omitted, never invented. This is a deliberate tightening of the original specification, which had allowed the model to "assume logical default values" when data was missing. The shipped prompt removes that latitude for the numeric and date fields, because a hallucinated capacity or budget would propagate as a design-relevant value into the crowd and placement stages. An omitted required field instead becomes a validation failure that triggers a retry.

The model's system prompt frames it as a backend data processor whose only function is extraction under the provided schema, instructs it to ignore any request outside the schema, and tells it never to design. The closed schema is described in the code as the *primary* structural guardrail and the prompt as secondary reinforcement: because the API-side schema sets additional properties to false, the model is physically unable to emit a field outside the permitted set. This is the mechanical core of "the LLM never designs" — it is enforced by the shape of the output channel, not merely requested in the prompt.

### 4.3 Structured output, not text parsing

The model is invoked through the Anthropic SDK's structured-output path, supplying the schema as an output configuration, at temperature zero. The implementation explicitly does not use the SDK's convenience `parse()` helper. The rationale is recorded inline and is a direct instance of the loop-termination discipline discussed next: the convenience helper hides the model's `stop_reason`, which would force the loop to judge success on response text rather than on the explicit completion signal. A two-schema design separates concerns: the single frozen contract schema is the source of truth, and an API-side schema is derived from it at load time by stripping the constraints the structured-output API does not itself enforce (numeric minimums, the date format, the version constant) while keeping the object shape, the enum, the required list, and the closed additional-properties flag. The SDK client is constructed with its own automatic retries disabled, so that the parser's own loop owns every retry and the iteration cap counts exactly.

### 4.4 Termination on `stop_reason`, with the cap as backstop

The retry loop is the clearest expression of the project's reliability discipline. Each attempt runs two gates. The first gate inspects the response's `stop_reason`: anything other than a normal end of turn is a failed attempt, and a model refusal is marked non-retryable so that the loop breaks rather than re-sending an identical prompt. The second gate parses the structured content, injects the version constant, runs the shared schema validator, and applies plausibility bands — capacity in a wide but finite range, budget likewise — that are explicitly described as removable garbage filters rather than business rules. Only when both gates pass does the loop return; that successful return, not the iteration counter, is the loop's primary terminator. The cap of three attempts is a backstop reached only on repeated failure, and on exhaustion the parser throws a terminal error and returns nothing rather than a guessed brief.

The catch logic discriminates failure types by exception class, never by string-matching a message. An infrastructure error — a server error, a rate limit, a connection failure — switches the model from sonnet to haiku and continues without feeding anything back into the prompt. A data error — malformed JSON, a validation failure — keeps the same model and feeds the specific error back into the next prompt as a correction instruction. This separation matters: an infrastructure failure should not consume the data-retry budget with an unchanged prompt, and a data failure should not waste a model switch.

### 4.5 Secrets and downstream flow

The Anthropic API key is read from the environment by the SDK; no key literal appears in source, and the command-line interface never prints it. Once produced, the parsed brief is written through a validate-then-write path: the brief is validated against its contract first, and only a contract-valid brief reaches `parsed_brief.json`. Downstream, the `date` drives the climate stage; the `theme` soft-filters material candidates and, in the deferred render stage, conditions the image prompt; the `capacity` sets the crowd-simulation agent count by the rule of one agent per hundred attendees; the `budget` enters the placement stop rule; and the optional time window bounds the daytime crowd timeline.

### 4.6 An honest caveat about the live path

Accuracy requires stating that, in the live FastAPI run pipeline, the rigorous TypeScript parser is at present not invoked. The run endpoint loads the brief by direct field passthrough, merging any body-supplied fields over a persisted demo brief, and the code comments document this as an intentional deferral consistent with the principle that the LLM never designs and is not a blocking stage. The parser is fully built, unit-tested, and live-tested against the real API behind an opt-in test, but its wiring into the running pipeline is future work. A reader should therefore understand Section 4 as documenting a complete, exercised component whose insertion into the live path is deferred, not as describing a step the running demo performs on every request. The lineup and stage-popularity inputs, discussed next, are a separate channel and were never part of the LLM's output.

---

## 5. The Climate Layer: A Real UTCI Field on a Shared Lattice

### 5.1 What the climate service is, and what it is not

The climate stage obtains a real Universal Thermal Climate Index field from infrared.city, a third-party urban-microclimate simulation service accessed through a held Python SDK. The service is the project's climate engine and, equally important, its master coordinate lattice: every downstream spatial artifact snaps to the lattice the climate stage establishes. The terminology is disciplined, and was sharpened by domain-expert review. The system computes UTCI through a radiation-based service; it is not a mean-radiant-temperature-only calculation, not a Ladybug/EnergyPlus workflow, and not a computational-fluid-dynamics solver. Airflow is not solved, and the documentation says so plainly rather than implying a "CFD-lite" capability. This candour is itself a design decision: it is cheaper to a project's credibility to state a limitation than to have a reviewer discover it.

### 5.2 Which simulations are used

The service can run a range of analyses — wind and pedestrian wind comfort, solar radiation, daylight, sun hours, sky view factor, thermal comfort, and thermal-comfort statistics. U-Shade uses the thermal-comfort (UTCI) analysis as its primary, pipeline-gating field, and uses three further analyses — direct sun hours, solar radiation in watts per square metre, and a heat-stress statistic — as diagnostic overlays computed once over a shared area. It does not use the wind, daylight, or sky-view-factor analyses; the absence of a solved wind field is the honest counterpart of the terminology discipline above. The UTCI call sequence resolves a weather file from the site location, filters it to the relevant period, builds the analysis area from the site polygon, and runs the area to completion, with a pre-flight preview step that checks tile count and cost before any paid compute is dispatched.

### 5.3 Constructing the heat grid

The service returns a fine grid in geographic coordinates, with valid data inside the polygon and not-a-number values outside it. The construction routine crops to the non-empty bounding box, projects longitude/latitude to UTM zone 31N exactly once and only through the dedicated coordinate module, resamples the native roughly one-metre grid onto the 6-metre master lattice by mean-aggregating native cell centres into each lattice cell with the south-west origin snapped down to integer metres, and emits every non-empty cell with its baseline UTCI recorded alongside its current UTCI. Sub-threshold comfortable cells are preserved at this stage; the decision to ignore cells below 26 °C is made later, at scoring time, not at write time, so the heat grid remains a complete physical record. The output artifact records its schema version, its coordinate system and units, the lattice origin and dimensions, and the list of cells.

The 6-metre resolution is the load-bearing choice here, and its rationale is explicit in the code: a one-metre master lattice over a festival site would exceed a hundred thousand cells and make the crowd snap and the greedy sort intractable, whereas six metres matches both human-scale shade granularity and a typical six-metre structural bay. The value is labelled assumed and is immutable once a run is accepted. The resampling deliberately uses spatial mean aggregation rather than nearest-neighbour sampling so that the coarser cell is a faithful average of the fine field rather than an arbitrary point sample.

### 5.4 Anchoring, weather, and provenance

A subtlety the paper records precisely: the codebase contains more than one site coordinate, and they differ by several hundred metres. The canonical site centroid used to anchor sun-position geometry and the weather context is a fixed constant for the demonstration venue, Parc del Fòrum in Barcelona; a recent change reconciled the weather anchor to that same canonical centroid so that the weather context and the heat grid anchor to one point, after an earlier drift of roughly 0.7 km between two hardcoded values was identified and removed. The live UTCI run, however, derives its centroid from the mean of the site polygon's vertices rather than from any constant, because the centroid is not load-bearing for the service call — it drives sun position over a site a few hundred metres across. The weather input is resolved from the service's own weather endpoint where possible, and on a weather-endpoint failure the system falls back to a labelled Barcelona EPW (real measured weather) source, recording the substitution explicitly rather than silently. The provenance discipline here is absolute: a UTCI field is recorded as grounded, and an EPW-sourced run records its weather source in the ledger so that the substitution is never hidden.

### 5.5 Permission-gating a paid service

The microclimate service is paid, per-simulation cloud compute, and the system treats accidental spend as a failure mode to be engineered against. The governing policy is a hard gate: no UTCI simulation is run without explicit owner permission each time. This is enforced in several layers. A live-call budget caps dispatches per client and raises an error beyond the cap, a backstop against retry storms rather than a primary terminator. A cross-call ledger counts cache-missing dispatches across calls. The manifest decides cache-first whether a call is needed at all, so that a cache hit on the site, date, and hour-band input hash returns the persisted artifact with zero live calls; in the running demo this means the climate stage spends nothing, because the grid is already on disk. The only live-fetch entry points are standalone scripts carrying explicit "authorized paid run" headers, and the crowd and daytime paths are forbidden by assertion from ever touching the paid service, with a dedicated purity test enforcing the prohibition.

### 5.6 The continuous daytime timeline

The system reframes climate from a single static snapshot to a continuous daytime timeline, on the principle that the tool only matters in daylight — at night there is no solar load and no shade is needed. The timeline runs on real hours, from 09:00 to 20:00, and the authorized daytime run fetches all twelve real hourly grids with no interpolation, each fetch windowing on that single hour's sun position, writing one grid per hour. A canonical hour — 14:00, the midpoint of the assumed 12:00–16:00 peak-heat band — is copied to the grid that the crowd simulation runs on. The hourly grids are produced once, under explicit authorization, and cached; the running system reads them rather than minting fresh paid compute.

### 5.7 Feeding the placer

The heat grid reaches the placement core through the demand-construction step, where each cell's thermal excess above the 26 °C comfort threshold is multiplied by that cell's crowd density. The join is on the integer lattice key, and the excess is clamped at zero so that a comfortable cell contributes nothing. This is the literal "hottest × busiest" crossing, developed in Section 8. The comfort threshold itself is cited to the specification and is reused, never re-inlined, by the acceptance gate's grounded-cooling floor, with the code repeatedly warning that the several copies of the constant must not be allowed to drift.

---

## 6. The Crowd-Simulation Layer

### 6.1 Two engines: one live, one archived

The crowd layer has had two engines, and the honest account of why the live one replaced the other is itself a design lesson. The current engine is JuPedSim 1.2.1, driving the Collision-Free Speed Model, in which agents of 0.12-metre body radius follow scripted journeys toward stage goals at a speed limited by local density and never overlap. The previous engine was a custom deep-reinforcement-learning crowd, trained with proximal policy optimization through Stable-Baselines3, with a six- or seven-float observation and a two-float velocity action. The reinforcement-learning stack was retired but not deleted: it remains in the repository as a dormant, reversible reference, its model card stamped as superseded, because external research rated the festival-to-primitive mapping of the new engine at only medium confidence and the project wanted a fallback until the new engine proved out on a real site.

The reason for the swap is recorded plainly. The learned policy's stage-reach gate failed: in its best curriculum it brought only 54.8 % of agents to their target stages against a locked 70 % bar, owing to an alignment-blind lateral-push lane artifact and a goal-snapping bug, and the gap was deferred rather than closed. The scripted-journey model makes reach essentially 100 % by construction, so the meaningful failure modes it can still expose are unreachable geometry and broken journey wiring rather than a policy that simply fails to arrive. This is a deliberate trade of a learned, novel mechanism for a scripted, verifiable one, and the project's own discipline forbids justifying a model by novelty: a crowd claim must travel with its validation, never with its sophistication.

### 6.2 The numpy pin and reproducibility

The choice of JuPedSim 1.2.1 rather than a later release is a reproducibility decision. The 1.4 series hard-requires numpy 2.2, and raising the base numpy to 2.x regresses a frozen density-clustering path with an allocation fault and risks the byte-reproducibility of cached results from earlier phases. Pinning JuPedSim to the 1.2 series keeps the project on numpy 1.26 and preserves that reproducibility. A validation fingerprint string binds every crowd-validation result to the engine identity — engine name, version, model, and agent radius — so that a result computed under one engine cannot be silently credited to another.

### 6.3 The persistent daytime field

The continuous daytime crowd is not eleven independent snapshots; it is one persistent simulation held across the whole festival day. A single simulation object is created and run across eleven hourly intervals from 09:00 to 20:00. At each hour boundary the per-stage demand is recomputed, a target headcount per stage is apportioned over the live population, and a popularity-delta cohort of agents is reassigned to the newly busier stages by the verified call that switches an agent's journey, whereupon those agents re-path and physically walk across the site. That walk is the visible migration. The reassignment is staggered over roughly the first third of each interval so that the crowd trickles rather than teleports. Two honesty invariants hold by construction: the agent count is constant, because migration is reassignment rather than spawning or removal, so the number shed equals the number received; and the selection is deterministic and free of random numbers, the lowest agent identifiers shed first.

### 6.4 Wiring the brief into the crowd

The central question the user posed — how the parsed brief drives the crowd to the right stages at the right times — is answered by a single demand formula. The crowd's spatial-temporal demand is

```
demand(hour, stage) = capacity_floor(stage) × draw(stage) × active(stage, hour) × occupancy(hour)
```

Each factor has a distinct origin. The `capacity_floor` is a per-stage-class weight — a main stage outweighs a secondary stage — derived from the stage's class. The `draw` is the stage's popularity pull, grounded in real listener data as described below. The `occupancy(hour)` is a site-wide arrival profile, the fraction of peak attendance present at that hour, capturing the festival's overall fill curve. The pivotal factor is `active(stage, hour)`, which is 1.0 when that hour falls within the stage's scheduled active hours and a small baseline value, 0.1, otherwise. That switch between 1.0 and 0.1 is precisely what makes the crowd migrate across the site as the live stage moves through the day. The capacity comes from the parsed brief and sets the agent count at one agent per hundred attendees; the schedule and popularity come from committed organizer inputs — a per-stage program table giving each stage's active hours and draw, and an occupancy curve. The demand vector for an hour is converted to an integer headcount per stage by deterministic largest-remainder apportionment, with every mapped stage floored at one agent, and those counts drive the journey switches.

The inputs are treated as hard requirements, not soft defaults. A missing program raises an error — no program, no run, with no assumed fallback rotation — and a program stage that is not present in the site's stage set raises an error rather than being silently dropped, because a phantom stage would be a route to spoofing the crowd field. This refusal to fabricate is the same discipline that governs the climate and material layers.

### 6.5 Stage popularity grounded in Spotify

The "draw" factor — how hard each stage pulls — is grounded in real data rather than guessed. A grounding script maps each headline act to its real Spotify monthly-listener count, captured by web research and explicitly not fabricated, and converts it to a continuous draw weight on a 1.0-to-5.0 scale by a base-ten logarithm of the listener count, anchored so that roughly twenty thousand monthly listeners map to 1.0 and roughly sixty-eight million map to 5.0, linear in log-listeners and clamped. The mapping is kept continuous, rather than bucketed into integer tiers, so that two very popular acts that differ by tens of millions of listeners still produce different pulls. The resulting per-stage draw values are written into the program tables and tagged as a grounded provenance tier.

The honest scoping around this grounding is meticulous. The popularity *driver* is grounded; the per-zone spawn split that distributes a stage's crowd across its immediate area remains an assumption; and the daytime program — which stage is live in which hour — is itself an illustrative demonstration table for the demo venue rather than a scraped real timetable. The night lineup is used as the stage brand-pull proxy for the daytime simulation. Critically, the project's discipline holds that popularity refines demand but does not gate acceptance: a wrong popularity weight can change where the crowd is estimated to gather, but it can never cause the cooling-acceptance gate to pass falsely.

### 6.6 The density field and its honest units

The simulation produces a trajectory array of agent positions and velocities over time. The density builder histograms terminal agent positions into the same 6-metre master lattice, reading the cell size from the heat-grid artifact so that the two grids are byte-aligned, and emits a per-cell crowd density in *agents per cell*. This unit distinction matters and the paper states it precisely: the crowd grid's native field is agents per 6-metre cell, not persons per square metre. Conversion to persons per square metre happens only at the coupling layer, where it is clamped at the Fruin crush ceiling of six persons per square metre, on the honest grounds that a real crowd cannot pack past the crush limit even where an over-subscribed waypoint cell in the simulation would suggest it.

The crowd grid also yields two higher-level products by density-based clustering (Ester et al., 1996): dwell zones, formed from agents whose speed stays near zero for more than ten consecutive steps and then clustered into convex-hull polygons, and flow vectors — the "invisible highways" — formed by clustering journey origins and destinations into a handful of major movement groups. The clustering is the frozen path that the numpy pin protects.

### 6.7 Validation against a real festival, and an honest failure

The crowd engine's magnitude is validated against real measured data, and the current verdict is a failure that the system reports rather than hides. The reference is the MADRAS dataset from the Lyon Fête des Lumières, a measured single-frame snapshot of more than four thousand people at the Place des Terreaux, binned to persons per square metre. The harness runs the same engine and the same walk-to-attractor-and-dwell mechanism on the real Lyon geometry with the real population, and samples density over the last twenty recorded frames — a locked settled-state window — comparing the simulated mean and high percentiles to the measured ones within a ±50 % band and checking that the simulated maximum does not breach the Fruin ceiling of six persons per square metre. What it validates is the magnitude regime, not the site-specific spatial allocation at the festival venue, for which no open data exists and which therefore stays assumed.

Under the locked settled window the gate currently fails: the simulated densities exceed both the percentile tolerance and the Fruin ceiling, and the on-disk benchmark artifact records the failure explicitly with `passed: false`. Consequently the crowd-density magnitude, which an earlier green run had promoted to derived, has reverted to assumed, and the whole crowd field is assumed-grade. The re-earn discipline is strict and worth quoting in spirit: the harness always records the honest result, a failing artifact keeps the tier assumed, and the gate is never loosened to pass — it is fixed only by fixing the settled run. A provenance gate downstream reads this artifact and holds the crowd density at assumed unless the benchmark is genuinely green and the engine fingerprint matches, so that no caller flag can flip the tier. This is, in the project's own framing, an honest correction rather than a bug: the Fruin breach genuinely fails the gate.

---

## 7. The Crowd–Heat Coupling: Metabolic Feedback as a Visualization-Layer Model

### 7.1 The physical claim

A crowd is a heat source, and at festival density it is a significant one. The system models a feedback in which crowd density raises the felt UTCI of the cells the crowd occupies, by three additive pathways. The first is sensible metabolic heat: a box model converts per-cell density to a sensible heat flux from the active festival-goers, divides by an air residence time set by the local wind and the cell size, and converts to a temperature rise through the volumetric heat capacity of air over a shallow near-ground mixing height. The second, and the dominant outdoor pathway, is blocked wind: a packed crowd removes a fraction of the near-ground breeze, and the lost wind is converted to a UTCI penalty. The third is added humidity from perspiration, scaled by density and by how still the local air has become. The three are summed and capped at a total of 4 °C.

The constants are stated honestly as mostly assumed. Per-person power is taken at 150 W, the midpoint between a standing-relaxed metabolic rate and active dancing; the sensible fraction at hot ambient temperature is taken at 0.36, with the explicit note that the comfortable-room value of about 0.67 does not hold at 30–35 °C; the mixing height, base wind, wind-block fraction, and the two conversion coefficients are each labelled assumed, while the air heat capacity and the Fruin density ceiling are derived physical constants. The total cap of 4 °C is justified as the observed bound from a sheltered-stadium study.

### 7.2 The honesty of an unmeasurable quantity

The entire coupling layer is labelled assumed end to end, and the supporting research note is unusually candid about why. A worked example in that note estimates that four persons per square metre dancing produce on the order of several hundred watts per square metre of sensible heat, the same order as midday solar load, locally — which is what makes the effect worth modelling at all. Yet the same note records that no open-air study cleanly isolates a crowd-only temperature rise at one to six persons per square metre, so the magnitude must remain assumed; the project would be the first to measure it, which is exactly why the layer ships labelled rather than asserted. The note mirrors established urban-energy-balance models — TEB, SUEWS, LUCY — as its lineage. The system never claims a measured "+N °C"; it presents a reasoned, bounded estimate and says so.

### 7.3 The load-bearing caveat: the feedback is visual, not placement-driving

The most important structural fact about this coupling, and one the user's brief specifically asked the paper to surface, is where it is wired. The crowd-to-heat function is real, deterministic, and literature-bounded, but in the current build it is consumed only by the frontend animation, which ports the same arithmetic into the browser to colour the live daytime field. The placement core's demand is built from the *raw* UTCI grid, not from the crowd-adjusted felt UTCI. The metabolic feedback therefore does not propagate into where shade is placed. The architecture diagram shows the feedback as a pipeline arrow, and conceptually it belongs there, but in code the arrow is realized in visualization rather than in the placement mathematics. The paper states this asymmetry plainly because it is exactly the kind of gap the project's honesty discipline exists to expose rather than paper over.

### 7.4 The reverse coupling, and its absence in the live engine

There is a symmetric question: do pedestrians avoid hot cells while walking? The honest answer is that heat-aversion in routing existed only in the retired reinforcement-learning engine, whose reward subtracted a penalty when an agent stepped onto a cell hotter than the comfort threshold, so that, in principle, heat shaped routing. That engine is dormant. The live scripted-journey engine has no heat term at all: agents are slowed by local density through the speed-density fundamental diagram, never by temperature. In the shipped product, therefore, the heat-and-crowd loop is effectively one-directional and visualization-only — crowd density tints the felt-heat picture for the viewer, but neither the placement nor the live routing closes the loop. This is a limitation the system is transparent about rather than one it obscures, and Section 17 returns to whether it matters for the tool's purpose.

---

## 8. The Placement Core: Maximal Covering by Greedy and Exact Optimization

### 8.1 Reframing shade placement as a covering problem

The placement core is where the system earns its central claim. The question it answers is: given a finite number of buildable structures and a demand field that combines heat and crowd, where should the structures go to protect the most at-risk people? Posed this way, it is a named, well-studied problem — the Maximal Covering Location Problem (Church & ReVelle, 1974). The reframing is itself a design decision, taken in the project's regenerative pivot, replacing an earlier greedy "shade-confetti" scorer with a covering formulation whose objective and constraints are explicit and whose solution quality can be reasoned about. The project's own brief on the pivot states the case: the new question is where to place *K* buildable structures to cover the most hot-by-busy demand, and that is a problem with a literature and guarantees rather than an ad-hoc heuristic.

### 8.2 The demand field

Demand is defined per lattice cell as the product of crowd density, a literature density-magnitude scalar, and thermal excess above the comfort threshold:

```
weight = crowd_density × density_magnitude × max(UTCI − 26, 0)
```

The clamp to zero is the mechanism that enforces one of the project's non-negotiables: a cell that is comfortable, or that has no crowd, has zero weight, is dropped from the demand field entirely, and can never become a coverage target or attract a structure. The system is barred from spending budget on shading hot ground that no one stands on, and equally from shading a crowd that is not hot. The density-magnitude scalar is fixed at unity and labelled assumed; because the greedy and exact selections are invariant to a positive global scaling of demand, it rescales the reported absolute demand without changing which cells are chosen. The two grids join on the integer lattice key, and a duplicate key raises rather than reconciles. The unit of demand is, fittingly, "agent-celsius" — the product of agents per cell and degrees of excess.

The thermal term here uses the raw UTCI, the consequence of the coupling asymmetry described in Section 7. The crowd-density term is assumed-grade, and by the weakest-input-wins rule the demand field, and therefore the placement, inherits the assumed tier — a fact the output artifact carries forward rather than hides.

### 8.3 Two solvers for one problem

The same covering problem is solved by two interchangeable engines, selectable by a stage parameter, and the relationship between them is the most elegant part of the design.

The **greedy solver** is the shipped default. It is a deterministic submodular maximum-coverage heuristic that repeatedly adds the candidate structure of greatest marginal newly-covered demand, with a total-order tie-break by lattice key then index so that the result is byte-stable regardless of the order in which candidates are presented. It carries the classical (1 − 1/e) ≈ 0.63 worst-case guarantee (Nemhauser et al., 1978), requires no solver dependency, and never blocks. Crucially, it makes no claim of optimality; the project enforces this with a test that forbids the word "optimal" anywhere in the core module's source.

The **exact solver** is a binary integer program solved with SciPy's interface to the HiGHS mixed-integer solver (Huangfu & Hall, 2018) — not PuLP and not OR-Tools, a detail worth recording because it determines the dependency surface and the certificate format. It introduces a binary selection variable for each candidate and a binary covered-indicator for each demand cell, maximizes the total covered demand (expressed as a minimization of its negation), and enforces two families of constraints: a coverage-linking constraint that lets a demand cell count only if some chosen site covers it, and a cardinality constraint limiting the number of chosen sites to *K*. A sub-unit lexicographic term is added to the selection variables to impose a deterministic ordering *within* the optimal face — proven smaller than the integer coverage gap so that it can never change which solution is optimal, only which of several equally optimal solutions is returned. The solver is run with presolve, a zero relative gap, and a time limit, single-threaded for reproducibility.

### 8.4 The candidate set, and why it is dense

A detail that protects the integrity of the exact solve is the candidate set. The candidates are a dense grid of lattice-cell centres, not a sparse set of clustered hotspots. The rationale, recorded as a pitfall, is that seeding the candidate set from density-based hotspot centroids would hand the solver a tiny feasible region and let an apparent optimum sit between the blobs, collapsing the meaning of the "optimal" claim. Feeding a dense candidate grid keeps the optimization honest. The coverage region of a candidate is pluggable; the production model is the projected shadow of the canopy footprint offset by the sun direction, so that a candidate covers the cells its shadow actually falls on rather than the cells directly beneath it.

### 8.5 The stopping rule: K primary, budget secondary, zero-gain honest

The stopping rule is identical across both solvers, and its precedence is deliberate. The primary terminator is the structure count *K*, defaulted to five and treated as an organizer input — "I can build this many canopies" — that cannot live in the frozen four-field brief and so is supplied as a stage parameter. The secondary cap is the budget: the loop stops before placing a structure it cannot afford, given an assumed per-structure cost. The third stop is an honesty stop: the greedy never places a structure of non-positive marginal gain, so it stops adding shade once no remaining candidate would cover any new demand. The exact solver inherits the same precedence, with *K* as the cardinality bound and budget as the secondary cap. This ordering — coverage target first, money second, never-place-useless-shade always — encodes the protective purpose of the tool: the goal is to cover the at-risk crowd, with cost as a constraint, not to spend a budget.

### 8.6 The greedy as a permanent witness on the exact solve

The relationship between the two solvers is the design's signature. On every exact solve, the greedy is run as well and retained as a lower-bound witness. A proven optimum can never cover less demand than a feasible heuristic; therefore, if the exact solver ever returns a covered demand below the greedy's, the model is wrong, and the system raises a cross-check error rather than trusting the number. This converts the greedy's 63 % worst-case bound from a weakness into a verifiable run-time invariant, and it guards against the silent modelling errors — a mis-built constraint matrix, a sign error — that are the real risk in an integer program. In the demonstration the exact objective equals the greedy covered demand exactly, so the realized gap is zero. A scale guard caps the constraint-matrix size and raises an over-size error rather than ever silently subsampling the demand or degrading to greedy; the exact solver either solves the real instance or refuses, never quietly solving a smaller one.

### 8.7 The optimality-vocabulary firewall

The project draws a sharp line between "optimal" as an unearned word and "proven-optimal with respect to this coverage model and this demand field, at gap zero" as an earned, qualified claim. The word "optimal" is forbidden in the core module by a test that globs its source, and is permitted only in the exact-solver package. When the exact solver proves optimality — status solved and gap exactly zero — it emits a single optimality certificate recording the objective, the gap, the solver and version, and a strictly derived `proven_optimal` flag. A time-limited or non-zero-gap incumbent fails loudly rather than claiming optimality. This is the difference, in the project's words, between an invented claim that is forbidden and a derived claim that is defensible, and it is enforced mechanically rather than by editorial care.

### 8.8 Output: ranked zones, and the design boundary

The placement core emits a `structure_zones` artifact: a ranked list of zones, each with its centre, area, marginal and cumulative demand, running coverage percentage, newly-covered cell count, and a robustness label drawn from a multi-scenario family that marks a zone as robust if it is selected across all snapshots or conditional if only some. The artifact contains no drawn-plan geometry, no part sizing, and no materials list — the placer never designs, by the same principle that governs the parser. The live full-run terminates here, at ranked zones; this is the system's deliberate boundary between machine proposal and human commitment, and it is examined in Section 14.

---

## 9. Material Selection and the Cooling Golden Rule

### 9.1 The catalogue

Cladding a structure requires choosing a material, and the system chooses from a catalogue of reclaimed archetypes. The catalogue began as ten frozen entries — five structural, five membrane — and was deliberately unfrozen by owner directive when the frozen cap began to constrain the work, growing to sixteen datasheet-sourced archetypes: seven structural and nine membrane. Each entry records an identifier, a display name, a structural-or-membrane type, a named real source and town, a quantity unit, theme tags for the soft filter, usage conditions such as maximum span and waterproofing, physical dimensions including thickness and unit mass, a real market cost, a solar transmissivity (a fraction, or null for materials that never serve as overhead cover), and a life-cycle profile giving the road distance to site and the transport-mode emission factor. The structural archetypes include scaffold tube, aluminium event truss, euro pallet, fence panel, stadium chair, reclaimed steel I-beam, and shipping-container corten panel; the membranes include billboard vinyl, industrial shade net, recycled tarpaulin, yacht shrink-wrap, festival carpet, marine sailcloth, cargo net, recycled sheet, and technical shade-cloth. Each entry's physical specifications are tied to a real datasheet or standard in a provenance ledger discussed in Section 10.

### 9.2 Transport-only carbon

Carbon is accounted on a recycled cut-off basis (ISO 14044, 2006): for a reclaimed object the manufacturing carbon is treated as zero, and only the transport is counted. The formula is a round trip — delivery and later dismantling — over the real road distance:

```
transport_carbon = 2 × distance_km × mass_tonnes × transport_mode_factor
```

with mass in tonnes computed from quantity and unit mass, and the transport-mode factor set to the UK government's 2024 average-laden heavy-goods-vehicle figure of 0.09752 kg CO₂e per tonne-kilometre (DEFRA/DESNZ, 2024). The factor of two for the round trip, the cut-off boundary, and the labelling of every carbon number as assumed are all explicit. A subtlety the paper records: a placeholder factor of 0.10 survives as an unused default in one selection module with stale documentation, but the live comparator and the marketplace both pass each material's own 0.09752 factor, so the production carbon numbers are at the DEFRA grade; the 0.10 default is effectively dead code. The marketplace carbon function returns a null rather than a fabricated number when quantity or distance is unknown, and computes a per-unit carbon from distance and unit mass alone so that a real number can be shown even when a scraped stock count is missing.

### 9.3 Distance over real roads

The distance that enters the carbon formula must be a road route, never a straight-line approximation, because a straight-line distance understates kilometres, understates carbon, and thereby overstates the green claim — a pitfall the routing module names explicitly. The router resolves through a provider ladder: a keyed routing service, then a keyless OSRM endpoint (Luxen & Vetter, 2011), and finally a deterministic offline fallback that multiplies the great-circle distance by a 1.30 road-circuity factor, calibrated to reproduce a verified real route from a supplier town to the site. Live routing is environment-gated, and the catalogue's distances are pre-fetched real routes recorded at the derived provenance tier.

### 9.4 The minimum-carbon comparator

The material selector, per zone, soft-filters the membrane candidates by the parsed theme — keeping materials whose theme tags include the brief's theme, and falling back to all candidates rather than crashing if none match — drops any candidate without a solar transmissivity (a structural material can never be the membrane), sorts the survivors by transport carbon, and selects the lowest-carbon *available* candidate. Availability is treated strictly as a filter, never as a re-ranking key: the sort key is carbon, and the selection is the first available material in carbon order, with the basis recorded as `transport_carbon_min` as an honesty marker that the choice was made on carbon and not on price. If no candidate is available, the selection is marked infeasible rather than forced. The decision to minimize transport carbon, rather than cost, is a value statement made explicit in the specification: sort by emission value and select the absolute minimum-transport-carbon option.

### 9.5 The Golden Rule: cooling scaled by one minus transmissivity

The relationship between geometry, material, and cooling is governed by what the project calls the Golden Rule, re-coupled in a specific amendment. Cooling is driven primarily by geometry — how much of the demand the shade's shadow covers — and is then corrected by the chosen membrane's optical quality. A loose-knit net that transmits much of the sun delivers less UTCI reduction than a solid membrane over the same footprint. The correction is one minus the solar transmissivity:

```
cooling = geometric_cooling × (1 − solar_transmissivity)
```

This correction enters the entire codebase in exactly one place, and the direction is guarded: a higher transmissivity yields a smaller factor and less cooling, which makes a leaky membrane *harder* to pass the acceptance gate, and a test asserts that a transmissivity of 0.40 yields less cooling than one of 0.15. The decoupling from carbon is equally strict: the carbon and cost computations carry no transmissivity argument, so they are byte-identical across transmissivity values. Cooling depends on the optics; carbon depends only on transport. The membrane transmissivities in the catalogue range from fully opaque (zero) to a loose net (0.45), and the user interface surfaces the implied shade percentage as one minus transmissivity. This single-site discipline is what lets the system say honestly that a particular layout cools by a particular margin: the margin is the geometric ideal scaled by a real, per-material optical factor, not an undifferentiated assumption that all shade is equal.

---

## 10. The Material-Sourcing Platform

### 10.1 From catalogue to a living supply

The catalogue of sixteen archetypes is the system's vocabulary of materials; the sourcing platform is what binds that vocabulary to real, currently available stock in the city around the site. The platform's ambition, parked as a second product phase under the name "Uber for Materials," is a regenerative material-harvesting marketplace that finds locally available reusable and waste materials across a city, maps them in real time, classifies them, and connects the people who hold them with the organizers who need them. In the system's framing this is the *supply* side, of which the crowd-by-heat placer is the *demand* side: shade goes where crowd and heat demand it, built from waste the platform harvests locally, designed by a human architect. The architecture is candid about the hard problem at the centre of any such marketplace: a claim against a scraped listing binds nothing, and a claim that does not bind is theatre. The first version is therefore scoped as a curated-supplier marketplace with a binding reserve, while computer-vision material detection and predictive forecasting are deferred to a research track.

### 10.2 The scrape adapters

The platform scrapes real reclaimed-stock sources through cache-first adapters that mirror the discipline of the climate network seam: a typed fetch error wrapping any HTTP or parse failure, a live-fetch budget cap as a backstop against retry storms, lazy import of the HTTP and scraping libraries inside the fetch method so the offline test suite stays network-free, and a fixed, SSRF-safe allow-list of base URLs that is never user-supplied. The adapter types include a Shopify-style adapter that reads public product feeds and uses per-variant availability as its signal, static-HTML scaffold-catalogue adapters, and a distinctive scheduled-surplus adapter described below. The active source allow-list spans real suppliers of truss, shade net, tarpaulin, and PVC, deliberately including some high-transport-distance sources, because the transport-only carbon model honestly penalizes a distant source rather than hiding it — that penalty is truthful, not greenwashing. One broad-catalogue plastics source was dropped after it false-bound large numbers of generic tubes and sheets to specific archetypes, a correction discussed under the classifier.

### 10.3 The scheduled-surplus adapter: a collect-before-landfill clock

The most conceptually interesting adapter does not scrape a product listing at all. The scheduled-surplus adapter reads a real, public municipal cultural-agenda record — a festival name and its published end date — and, through a deterministic festival-kit inference table, emits the standard reusable hardware that a festival teardown sheds: truss, fence, pallets, carpet. Each is bound to a catalogue archetype by the shared classifier with no new rule. The honesty seams here are explicit and instructive: the snapshot is labelled at the assumed tier; quantity is never asserted, because there is no ground truth before teardown; availability stays unknown, because the gear is not yet dismantled; each listing carries an availability window from the end date to a few days later, flagged as an end-date proxy because the published date is a slipping plan rather than a hard expiry; and the live municipal resource identifier is environment-gated, because guessing it would fabricate provenance. The adapter raises rather than hit a guessed endpoint. The idea — treating a festival's own end date as a clock that starts a collect-before-landfill window on reusable structure — is the regenerative thesis of the platform reduced to a single data source.

### 10.4 The deterministic classifier

Binding a scraped listing to a catalogue archetype is done by a purely deterministic rule engine, and the decision to make it deterministic rather than learned is one the project defends sharply. There is no model inference, no vector similarity, and no fuzzy best-guess anywhere in the classifier; the test the project applies to itself is, if the model were removed, which decision would change — and the answer is none. The classifier works in two stages. A coarse-class stage scans the listing's text, in Spanish and English and accent-insensitively, for membrane and structural keywords, and rejects a listing that matches both classes or neither. A specific-type stage applies a table with one rule per archetype, each requiring all of a set of synonym groups and an optional numeric dimension gate; exactly one match binds, zero matches or more than one match reject. A dimension gate that is absent does not block a keyword-supported bind, but a gate that is present and out of bracket fails — a sixty-millimetre tube cannot bind to a forty-eight-millimetre scaffold archetype. Untrusted scraped dimension values are coerced safely, returning null on a parse failure rather than crashing.

The conservation guarantee is the classifier's analogue of the placement infeasibility report: the batch classifier returns accepted and rejected lists whose lengths sum to the input, and every rejection carries a non-empty reason, a title, and a source URL. Nothing vanishes silently. This discipline caught a real greenwashing failure: a bare "shrink" token had bound dressmaking-fabric listings — "shrink-resistant jersey" — to a maritime shade material, so the rule was tightened to require a marine or polyethylene qualifier alongside the shrink token, and the apparel-fabric shops were retired from the active scrape set entirely. The project's directive is to add only materials genuinely viable as festival shade or structure, never apparel or dressmaking fabric, and to keep carbon and transmissivity labelled honestly.

### 10.5 The pipeline: scrape, classify, route, de-duplicate, bind

The inventory stage runs cache-first and degrades in a labelled, never-silent way: a fetch failure produces a labelled stale or unavailable state rather than an empty live result, and a fetch that succeeds but binds zero listings is labelled unavailable and carries the rejection records, never a fabricated binding. Scraped Shopify variants of the same product are de-duplicated into one golden record whose quantity sums the known variant quantities and whose availability takes the strongest variant signal, with the rollup count recorded and conservation checked. The recent unification that the frontend masthead summarizes as "22 sources, 30 km span" is precisely this: the sixteen-archetype catalogue merged with the distinct live-scraped sources into one list, the thirty kilometres being the span to the farthest source. Per-item carbon is unchanged by the merge, because it is derived from each item's own distance rather than from the range label.

### 10.6 Provenance ledger and research foundation

The material specifications are not asserted; they are sourced and tiered. A provenance ledger records, per material and per field, a tier and a citation — grounded for a real datasheet, EPD, or standard; derived for a computed value; declared for an honest estimate with no source. The specifications were assembled in a single deterministic pass that loads the catalogue, applies a table of per-material values with their tiers and citations sourced in an earlier data-understanding phase, sets the transport factor to the DEFRA figure, fixes the distances to real routes, and writes the ledger, self-reporting a coverage tally of grounded-plus-derived fields. The research that underlies the catalogue draws on external reclaimed-material studies and a Barcelona materials atlas; the paper records honestly that two of those source artifacts are cited but are not themselves checked into this repository, surviving only as the archetypes they seeded and the supplier table they informed. The CRISP-DM phase directories for business understanding and data understanding are present and document the decision statement, output specification, success criteria, data inventory, and profiling plan that preceded the build.

### 10.7 Material imagery, with a three-tier honesty ladder

Each archetype carries an illustrative image, and even the images obey the provenance discipline. The sixteen images were regenerated as studio close-ups of the actual material on a neutral background, after an earlier set wrongly showed the *source object* — a boat for shrink-wrap, a billboard for vinyl — rather than the reclaimed material itself. The display obeys a three-tier ladder: a real supplier photograph is shown plain and always wins; otherwise the archetype illustration is shown but always badged as a reference or AI illustration, a picture of the material type rather than the actual stock; otherwise an honest "no image yet" placeholder appears, never a broken image. The accompanying note warns explicitly that the illustrations are not photographs of real reclaimed stock and must never replace a real photo.

### 10.8 The client's role: recommend, not reserve

The materials interface evolved in a way the paper records because it reverses an earlier decision. Originally the system selected the material per zone and the client interface was read-only evidence, with no hold or reserve controls — the client did not choose. The current design has the system recommend a shortlist of three to five strongest materials, ranked on cost, carbon, and ease of assembly, from which the human architect designs; nothing is reserved in the interface. The full catalogue is surfaced alongside, with each entry marked bindable only if a live or onboarded listing actually exists, and the rest shown as honest reference entries. The supply side is bootstrapped by onboarding real atlas operators as suppliers, each unverified until a human admin gate verifies them, because trust is a human decision and never self-asserted.

---

## 11. The Cooling Acceptance Gate

### 11.1 Purpose: proving the layout cools

A shade layout that covers the busiest, hottest cells is only useful if it actually reduces felt temperature, and the system refuses to assume that it does. A dedicated acceptance gate certifies the cooling claim against two pre-declared thresholds. It checks coverage — the percentage of the funded hottest-by-busiest priority cells whose centre falls within the projected shadow of the placed structures — and it checks the mean UTCI reduction over that same shaded priority set. The reduction per cell is the geometric ideal scaled by one minus the membrane transmissivity, measured against each cell's persisted baseline UTCI, which is read and never re-derived, so the gate never triggers a second paid climate call. The ideal full-shade reduction is an assumed 8 °C, declared as a conservative peak-hour opaque-canopy benefit and explicitly not back-fitted to make the demo pass; with the demonstration membrane's transmissivity of 0.40, the realized reduction is eight times six tenths, or 4.8 °C, which clears the threshold through the real optical path rather than through a tuned number.

### 11.2 Coverage by projected shadow, not footprint

A cell is credited as shaded only if its centre falls inside the *projected shadow*, not merely under the footprint. The distinction is deliberate honesty about sun geometry: once the sun is off-zenith, a tall, thin canopy footprints one cell yet casts its shade onto another, so crediting footprint area would overstate protection. The shadow is computed by parallel projection of each roof vertex along the sun vector, with a guard against a sun at or below the horizon, and the geometry is byte-deterministic. The coverage computation translates both the cell centres and the shadow to a common frame before the point-in-polygon test, so that a non-empty shadow never reads as a false zero. An earlier bug that inflated the shaded denominator to the venue-scale convex hull — and would have falsely failed the gate — was fixed by taking the true union of footprints rather than their hull.

### 11.3 Both criteria required, and a failure that is a valid outcome

The verdict is a logical conjunction: the layout passes only if coverage meets its threshold *and* the mean reduction meets its threshold. The conjunction is structural; a disjunction is forbidden by a plan-level check. The most important behavioural property of the gate is that a failure is a *successful stage outcome*. A failing verdict is written to disk as a real artifact and the stage is marked done; the fail-safe path that writes no artifact is reserved strictly for genuine internal errors, such as a missing upstream input or a tampered threshold. Routing a real failure through the fail-safe would be a silent non-run, which is exactly the violation the discipline exists to prevent. In the specification's phrase, "it ran to completion" is not a pass bar. The demonstration verdict passes, at full coverage and a 4.8 °C reduction against a 4 °C threshold, but the machinery is built so that a genuine failure would be reported as such rather than suppressed.

### 11.4 Hash-locked thresholds and a run-time tripwire

The two thresholds — a 4 °C minimum reduction and a 70 % minimum coverage — are the values most vulnerable to the cardinal dishonesty of a design tool: quietly relaxing a bar to make a borderline run pass. The system defends against this with a tamper-evident mechanism. The thresholds live in exactly one content-hashed file, declared on a fixed date and marked immutable, and the runtime loader recomputes the canonical-JSON hash of the threshold block on every load and raises a drift error if it diverges from the stored hash. A post-run edit of a threshold therefore fails at run time, not merely in a test, and no second copy of either numeric value is permitted anywhere else in the acceptance source. The thresholds were declared in the project's contract phase, before any results existed, and the project's framing is unambiguous: tuning a threshold to pass is the cardinal honesty violation the entire ledger exists to prevent.

### 11.5 A note on wiring

For completeness and accuracy: the acceptance gate, like the material and geometry stages, exists in the codebase and is exercised in the demonstration project, but it is one of the stages the live full-run no longer chains, the run terminating at ranked zones. The gate is therefore best understood as a fully built certification stage in the contract that the human-committed-design path would invoke, rather than as a step the current live demo runs on every request. This is the same proposal-versus-commitment boundary discussed next.

---

## 12. Structural Geometry: Built, Verified, and Deliberately Dropped

The original pipeline included a structural-geometry stage that turned a placed canopy into real fabricable structure using Rhino.Compute and Grasshopper, with Karamba for structural analysis, tilting each roof's pitch perpendicular to the sun vector to maximize projected shadow and applying standard wind-load vectors. This stage was genuinely built and verified end to end: a live bridge returned real pillar counts and membrane areas from a real Grasshopper solve with a specific Karamba version, with one known output-parameter issue remaining and the compute server still to be installed by the owner.

The stage was then deliberately dropped in the regenerative pivot. The governing reconciliation is that the principle "the tool never designs" was sharpened to "the engine proposes concepts seeded from the system, and a human commits." Generating fabricable structure is design, and design belongs to a human architect. The geometry stage was retired from the full-run, the geometry endpoints became honest empty states that return a not-found status rather than fabricated geometry, and the live pipeline's terminus moved to the ranked zones. The reinforcement-learning crowd engine and the geometry engine were both retained in the repository as reversible references rather than deleted, so that the decision is reversible, but the live system stops at proposal. This is not a capability the system lacks by accident; it is a boundary it draws on principle, and the next section describes the deliverable that boundary produces.

---

## 13. The Frontend and "The Plan" Deliverable

### 13.1 The wizard

The user-facing application, named U-Shade, is a single-route React application rendering one persistent Mapbox canvas, through which the organizer moves in an ordered wizard: Brief, Site, Layout, Shade, Materials, and The Plan. The Brief step captures capacity, budget, date, and theme together with the lineup; the Site step draws the boundary polygon with a live area readout; the Layout step places stages and amenities and triggers the run; the Shade step presents the ranked accept-or-keep shade zones once the simulation completes; the Materials step presents the reclaimed-stock review; and The Plan step presents the merged deliverable. A welcome screen offers three doors: create a festival from a hand-drawn site, try the Parc del Fòrum demonstration, or step into the "Beyond Festivals" concept mode. The map is a single instance mounted once, in a dark style, with heat, crowd, and ranked-zone overlays drawn with deck.gl and the boundary drawn with the Mapbox drawing control; the access token is read from the environment and never hardcoded.

### 13.2 The Plan

The architect hand-off and the report were merged, by owner directive, into a single editorial document called "The Plan," and a deliberate decision was made to show no price anywhere in it. The structure runs from a masthead and a hero datum — the percentage of the in-heat crowd now under shade and the number of structures to design, the cooling figure sourced from the real acceptance reduction — through a list of the structures to design, each described by its nearest landmark, its coverage target, and its orientation against the afternoon sun but deliberately without a square-metre footprint, since the tool does not design form. It continues through the recommended three-to-five materials with their reasons, distances, and scores, a four-milestone timeline, and a price-free "receipt" of four honest figures: people shaded, the cooler covered crowd, transport carbon, and the reclaimed-materials count. A method line closes the document by tracing the provenance of the result: the boundary the organizer drew, the real infrared.city heat grid, the crowd flow simulated across the day, and the hottest, busiest spots ranked for shade.

The research behind the deliverable reframes what an organizer is buying. The governing insight is that organizers are not buying shade; they are buying defensible proof that they discharged their duty of care, whose ultimate audience is an authority, an insurer, or an inquest. The deliverable is structured around four jobs — protect people, save money, design appropriately, and defend the decision upward — and it draws its presentation patterns from established professional tools: click-to-inspect interaction, a zero-to-hundred priority score, a ranked "shade desert" list, a before-and-after cooling hero, and a one-click exportable document. Each interface slice is reviewed by a visual-design agent, on the owner's standing instruction that a visual-expert check is always applied.

---

## 14. Site-Generality and the "Beyond Festivals" Mode

### 14.1 Any drawn boundary

A recurring discipline is that the engine must work for any site, with the demonstration venue treated as a fixture rather than a hardcoded target. The site boundary is an input: a request may supply a boundary polygon whose outer ring becomes the site geometry, and the demonstration venue is only a fallback default. A one-click loader fetches the committed demonstration schema and drops its boundary in as editable geometry exactly as a hand-drawn boundary would be, with the computed area — about 37.8 hectares — surfaced live. The points of interest render read-only, since they are a fixture for the demo, not a constraint on a general site.

The scale guards are honest rather than cosmetic. When an instance would exceed the integer program's constraint-cell ceiling, the system raises an over-size error before building the constraint matrix, rather than silently subsampling the demand or degrading to the greedy heuristic. The ceiling is sized on the binding dimension — demand cells times candidate sites — and read from the heat-grid artifact rather than from any venue-specific literal. The principle is that scale guards raise honestly and never quietly reduce the problem to keep a promise of generality it cannot actually keep at that size.

### 14.2 Beyond festivals

The "Beyond Festivals" mode is a demonstration that the engine is fundamentally a function of a timeline, a set of attractors, and a heat field, and is therefore site-general beyond festivals. It runs four concept scenarios — a city park, a school playground, a transit plaza, and a beach promenade, each on a real Barcelona location — through the same animated daytime-field component the festival mode uses, supplying override bounds and animation data so that the identical bilinear projection, crowd-to-heat coupling, iso-contour rendering, and worst-cell crosshair run on synthetic data. The scenario placement panel re-skins the festival's ranked-zone list on synthetic zones. The mode's value is argumentative: it shows that the same machinery that shades a festival can shade a playground at recess or a plaza along a commute, that the engine generalizes from "festival" to "any place where a crowd gathers under the sun on a schedule." The scenario state is fully isolated from the festival application state, so the demonstration cannot contaminate a real run.

---

## 15. Provenance and Honesty Engineering

The mechanisms described piecemeal in the preceding sections constitute a coherent design subsystem in their own right, and this section consolidates them, because the system's most transferable contribution may be its treatment of honesty as an engineered property rather than a documentation style.

### 15.1 The tier vocabulary as a type system for trust

Every reported quantity carries one of four tiers — grounded, derived, assumed, or declared/placeholder — and the tiers compose by a weakest-input-wins rule, so that a derived quantity built on an assumed input is itself assumed. This is, in effect, a type system for trust: it makes the epistemic status of a number a first-class property that travels with it through the pipeline and into the deliverable. The baseline UTCI is grounded; coverage and the cooling reduction are derived; the ideal full-shade reduction, the crowd density magnitude, and the metabolic-heat constants are assumed; a euro-per-degree figure becomes a placeholder null rather than a fabricated zero when its inputs are missing. The deliverable is permitted to claim only what the tiers support, and the single most-requested professional metric — cooling per euro — is held back to a labelled null until the cost inputs are real, rather than shown as a confident but baseless number.

### 15.2 Tamper-evidence and run-time integrity

Two mechanisms make the honesty active rather than passive. The first is the threshold tripwire: the acceptance thresholds are content-hashed and verified on every load, so an edit to make a result pass fails at run time. The second is the optimality-vocabulary firewall: the word "optimal" is forbidden by test in the heuristic core and permitted only in the exact-solver package, and the earned optimality claim is confined to a single certificate produced only at a proven zero gap. Together these encode a stance: the two ways a design tool most easily lies — relaxing an acceptance bar and overstating solution quality — are each blocked by a mechanical guard rather than left to discipline.

### 15.3 Never-silent degradation

Throughout the pipeline, a failure or a substitution is labelled rather than hidden. An EPW weather fallback records its source; a fetch failure produces a labelled stale state rather than an empty success; a scrape that binds nothing is labelled unavailable and carries its rejection reasons; a partial microclimate result with any failed tile raises rather than return a holey lattice; a crowd validation that fails writes a failing artifact and reverts the tier. The recurring rule is that the system would rather raise, label, or return a typed null than emit a number that looks confident and is not. This is the same instinct, applied to data, that confines the language model to translation: in both cases the design refuses to let a fluent-looking output stand in for a grounded one.

### 15.4 Determinism as a precondition for honesty

Honesty about a number presupposes that the number is reproducible. The system is deterministic by construction: a fixed seed makes the crowd field byte-identical across runs, the greedy and exact placements are byte-stable under a total-order tie-break, the shadow and coverage computations are pure, and the climate and acceptance stages cache on content hashes of their real inputs. Reproducibility is what makes a provenance tier meaningful — a "grounded" value that changed from run to run would be grounded in nothing — and it is what lets the cross-check between greedy and exact, or between a cached and a fresh artifact, be exact rather than approximate.

---

## 16. Evaluation and Validation Status

This is a systems paper, and its evaluation is correspondingly a status report on what each subsystem's own acceptance machinery currently certifies, rather than a controlled experiment. Reporting that status honestly is consistent with the system's own discipline.

The **climate field** is grounded: it is a real UTCI field from a real microclimate service, recorded with its weather source, on a fixed lattice. Its principal assumed inputs are the 6-metre resolution and the peak-heat hour band, both declared and immutable. The **crowd field's magnitude** currently fails its validation: against the real measured Lyon reference, the simulated densities breach both the percentile tolerance and the Fruin crush ceiling under the locked settled-state window, so the on-disk benchmark records a failure and the magnitude is labelled assumed; the spatial allocation — which cells are busiest — is assumed in any case, because no open data measures crowd density inside the venue. The **placement** is exact where the integer solver is used: it emits a proven-optimal certificate at a zero gap with respect to its coverage model and demand field, cross-checked against the greedy lower bound, with a realized gap of zero in the demonstration. But because the demand field inherits the assumed crowd tier, the placement's *demand* numbers are assumed even though its *optimization* is proven. The **cooling reduction** is derived: the geometric ideal is assumed, but it is scaled by a real per-material optical factor and measured against a grounded baseline through a single, sign-guarded correction, and the acceptance gate certifies the demonstration layout at full coverage and a 4.8 °C reduction against pre-locked 4 °C and 70 % thresholds. The **carbon** numbers are assumed by the cut-off boundary but computed from a grounded emission factor over real road distances. The **material specifications** are predominantly grounded or derived against real datasheets and standards, recorded in a per-field provenance ledger.

The honest summary is that the system's geometry and optimization machinery is rigorous and largely proven, its physical inputs are a mixture of grounded and assumed values each labelled as such, and its single most consequential open validation — the crowd density magnitude — currently fails and is reported as failing. A reader looking for a claim of end-to-end measured cooling will not find one here, and the absence is by design: the system distinguishes what it has proven from what it has assumed, and declines to blur the two.

---

## 17. Discussion

### 17.1 Why the language model is confined to translation

The decision that most shapes the system is the confinement of the language model to parsing. The defense rests on three observations. First, the design task is auditable and bounded — a covering optimization over an explicit demand field — and an auditable task is better served by an algorithm whose every step can be inspected than by a generative model whose reasoning cannot. Second, the honesty discipline is incompatible with a generative design path: a system that labels every number with a provenance tier, that forbids tuning a threshold to pass, and that refuses to claim optimality it has not proven cannot hand the design to a model that would produce fluent, unattributable, untiered output. Third, the confinement is enforced mechanically, by a closed output schema, rather than merely requested, so that the guarantee does not depend on the model's compliance. The cost of this decision is that the model cannot contribute design ideas; the benefit is that every design decision the system makes is one it can defend. For a tool whose ultimate audience is an insurer or an inquest, that trade is the right one.

### 17.2 Why maximal covering, and why two solvers

Formulating shade placement as a maximal covering problem buys a literature, a guarantee, and a vocabulary for solution quality that an ad-hoc scorer cannot offer. The two-solver design then resolves a tension between pragmatism and rigour: the greedy default never blocks, carries a known bound, and ships without a solver dependency, while the exact solver provides a proven optimum when one is wanted. The decision to keep the greedy running as a permanent lower-bound witness on every exact solve is the most defensible single choice in the placer, because it turns the heuristic's worst-case bound into a run-time correctness check on the integer program — the component most prone to silent modelling error. The dense candidate set and the over-size guard that raises rather than subsamples are the supporting decisions that keep the "proven optimal" claim meaningful.

### 17.3 The coupling asymmetry, and whether it matters

The paper has been candid that the crowd-to-heat metabolic feedback is wired only into the visualization and that the live engine has no heat-aversion in routing. Two questions follow: is this a defect, and does it undermine the tool's purpose? It is a limitation, not a defect, and its impact on the tool's purpose is small for a defensible reason. The placement demand already crosses crowd density with raw thermal excess, so the shade still goes where the hot and the busy coincide; adding the felt-heat feedback would sharpen the magnitude of the hottest cells but is unlikely to relocate the protected zones, because the feedback is largest exactly where the crowd is densest, which is already where the demand is highest. Heat-aversion in routing would, if anything, move the crowd *away* from the hottest cells, reducing the very overlap the tool seeks to protect; its absence is conservative for the protective objective. The honest position is that closing the loop is worthwhile future work whose primary value is fidelity of the visualization and of any future felt-heat reporting, not a correction that would move the recommended shade. Stating this is preferable to either hiding the asymmetry or overstating its consequences.

### 17.4 Why honesty is engineered, not asserted

A design tool that produces confident numbers invites trust it may not have earned, and the failure mode is not malice but drift: a threshold relaxed under deadline, a fallback that silently substitutes, an "optimal" that means "best I found." The system's response is to make each such drift fail loudly — a hashed threshold, a labelled fallback, a firewalled vocabulary, a validation that reverts a tier on failure. The deeper rationale is that the tool's value to its real audience is proportional to its defensibility, and defensibility is a property that must be built in, not added afterward. The crowd validation that currently fails is the clearest vindication of this stance: a system without the discipline would have shipped a green number, whereas this one reports the failure and holds the tier at assumed until the settled run is genuinely fixed.

### 17.5 Specification-versus-implementation divergences

Several places where the running system diverges from its specification have been recorded as they arose, and they are worth gathering, because a paper that claimed the specification was the system would be the kind of confident-but-untrue artifact the system is built to avoid. The Node orchestrator was never built as a server; FastAPI is the single backend, and the only Node code is the parser command-line tool. The rigorous parser is built and tested but not yet wired into the live run, which passes the brief through directly. The geometry, material, acceptance, and render stages exist but are not chained by the live full-run, which ends at ranked zones. The installed framework and numpy versions differ from the recommended ones for documented reproducibility reasons. None of these divergences is hidden in the codebase — each is documented at the point of divergence — and recording them here is the paper's way of honouring the same discipline it describes.

---

## 18. Limitations

The limitations follow directly from the honest evaluation and are stated without mitigation.

The crowd-density magnitude is not validated: under the locked settled-state window it fails the Fruin ceiling and the percentile tolerance against the real Lyon reference, and the spatial allocation of the crowd within the venue is assumed in any case. Any claim about how many people a layout protects inherits this assumed tier.

The crowd-to-heat metabolic coupling, though modelled and literature-bounded, is wired only into the visualization and does not influence placement; its magnitude is unmeasurable from current open data and is labelled assumed throughout. The reverse coupling, heat-aversion in routing, is absent from the live engine.

The cooling claim rests on an assumed 8 °C ideal full-shade reduction; while it is scaled by a real optical factor and measured against a grounded baseline, no measured shaded-versus-unshaded UTCI field exists to validate the ideal, and the measured-delta field is deliberately held as a null placeholder pending a field protocol.

Airflow is not solved; the UTCI field is radiation-based, and the only wind treatment anywhere is an assumed constant inside the visualization-layer coupling.

The carbon accounting omits manufacturing by the cut-off convention and counts only transport; it is therefore a transport-carbon comparison, defensible as such but not a full life-cycle figure, and every carbon number is labelled assumed.

The live pipeline terminates at ranked zones; geometry, material selection, the cooling gate, and rendering are built but not chained, so the running demo does not itself produce the certified-cooling, materially-specified deliverable end to end. That deliverable is assembled along the human-committed-design path that the contract describes.

Finally, the system is demonstrated on a single venue, and while it is architected for any drawn boundary and guarded against silent subsampling at scale, its generality beyond the demonstration site and the four concept scenarios is argued rather than empirically established.

---

## 19. Conclusion

U-Shade is a climate-aware shade-placement system that crosses a real thermal-comfort field with a real crowd-density field to place shade where heat and people coincide, selects the lowest-transport-carbon reclaimed material to build it, and certifies that the result cools through a gate it cannot quietly relax. Its architecture is a deterministic, sequential pipeline in which a language model is confined to translating a brief into four typed fields, a microclimate service supplies a UTCI grid on a shared six-metre lattice, a scripted-journey pedestrian engine migrates a crowd across a continuous daytime timeline driven by the real schedule and by popularity grounded in listener data, a maximal-covering optimizer places structures by both a bounded greedy heuristic and an exact integer program that cross-checks against it, and a material layer chooses cladding by minimum transport carbon scaled by real optical transmissivity.

The system's most distinctive property is not any single algorithm but the discipline that binds them: every number carries a provenance tier, every acceptance threshold is tamper-evident, every degradation is labelled, and the one validation that currently fails is reported as failing rather than dressed as a success. The same discipline draws the system's boundary at proposal rather than commitment, handing form-making to a human architect, and it is the reason the divergences between specification and implementation are documented rather than concealed. For a tool whose value lies in being defensible to an authority, an insurer, or an inquest, that discipline is the contribution. The work that remains — validating the crowd magnitude, closing the heat-crowd loop in the placement mathematics, grounding the cooling ideal against a measured field, and chaining the certified deliverable end to end on the live path — is named here precisely so that it can be earned rather than assumed.

---

## Declarations

**Data availability.** The system's artifacts, contracts, provenance ledgers, and planning records are held in the project repository. The reclaimed-material specifications are sourced to public datasheets and standards recorded in a per-field provenance ledger; two cited external research artifacts (a reclaimed-material study and a Barcelona materials atlas) are referenced but not redistributed in the repository. The crowd-validation reference derives from the publicly available MADRAS Lyon dataset under its stated open licence.

**Ethics.** The system processes no personal data. Crowd modelling operates on synthetic agents parameterized by aggregate capacity, not on identified individuals. The intended use is protective — reducing heat exposure at mass gatherings — and the deliverable is explicitly framed as decision support for a human decision-maker, not as an autonomous design authority.

**Conflict of interest.** The system is associated with a pre-seed commercial venture (per-event licensing and an annual pass) whose business assumptions are labelled as such; this paper documents and defends design decisions and does not constitute an investment representation.

**Author contributions (CRediT).** Conceptualization, methodology, software, and writing of the system and its governing decisions are the work of the project owner. This manuscript was prepared as a documentation and synthesis exercise over the existing codebase and planning records.

**Funding.** No external research funding supported the preparation of this manuscript. Commercial funding plans for the venture are described in the project's business documents and are not a funding source for this work.

**Use of AI tools.** This manuscript was drafted with the assistance of an AI system that read the project's source code and planning artifacts to extract and organize factual content. All technical claims are grounded in the repository; the foundational external references are cited from established literature. The authorial responsibility for accuracy rests with the project owner, and the manuscript deliberately records, rather than smooths over, the points at which the implementation diverges from its specification.

---

## References

Allen, L., Lindberg, F., & Grimmond, C. S. B. (2011). Global to city scale urban anthropogenic heat flux: Model and variability. *International Journal of Climatology, 31*(13), 1990–2005.

ASHRAE. (2023). *ANSI/ASHRAE Standard 55-2023: Thermal environmental conditions for human occupancy.* American Society of Heating, Refrigerating and Air-Conditioning Engineers.

Bröde, P., Fiala, D., Błażejczyk, K., Holmér, I., Jendritzky, G., Kampmann, B., Tinz, B., & Havenith, G. (2012). Deriving the operational procedure for the Universal Thermal Climate Index (UTCI). *International Journal of Biometeorology, 56*(3), 481–494.

Church, R., & ReVelle, C. (1974). The maximal covering location problem. *Papers of the Regional Science Association, 32*(1), 101–118.

Department for Environment, Food & Rural Affairs / Department for Energy Security and Net Zero. (2024). *Greenhouse gas reporting: Conversion factors 2024.* UK Government.

Ester, M., Kriegel, H.-P., Sander, J., & Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. In *Proceedings of the Second International Conference on Knowledge Discovery and Data Mining (KDD-96)* (pp. 226–231).

Fruin, J. J. (1971). *Pedestrian planning and design.* Metropolitan Association of Urban Designers and Environmental Planners.

Huangfu, Q., & Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. *Mathematical Programming Computation, 10*(1), 119–142. (HiGHS solver.)

International Organization for Standardization. (2005). *ISO 7730:2005 — Ergonomics of the thermal environment.* ISO.

International Organization for Standardization. (2006). *ISO 14044:2006 — Environmental management — Life cycle assessment — Requirements and guidelines.* ISO.

Järvi, L., Grimmond, C. S. B., & Christen, A. (2011). The Surface Urban Energy and Water Balance Scheme (SUEWS): Evaluation in Los Angeles and Vancouver. *Journal of Hydrology, 411*(3–4), 219–237.

Jendritzky, G., de Dear, R., & Havenith, G. (2012). UTCI — Why another thermal index? *International Journal of Biometeorology, 56*(3), 421–428.

Luxen, D., & Vetter, C. (2011). Real-time routing with OpenStreetMap data. In *Proceedings of the 19th ACM SIGSPATIAL International Conference on Advances in Geographic Information Systems* (pp. 513–516). (OSRM.)

Masson, V. (2000). A physically-based scheme for the urban energy budget in atmospheric models. *Boundary-Layer Meteorology, 94*(3), 357–397.

Nemhauser, G. L., Wolsey, L. A., & Fisher, M. L. (1978). An analysis of approximations for maximizing submodular set functions — I. *Mathematical Programming, 14*(1), 265–294.

Oke, T. R., Mills, G., Christen, A., & Voogt, J. A. (2017). *Urban climates.* Cambridge University Press.

Raffin, A., Hill, A., Gleave, A., Kanervisto, A., Ernestus, M., & Dormann, N. (2021). Stable-Baselines3: Reliable reinforcement learning implementations. *Journal of Machine Learning Research, 22*(268), 1–8.

Sailor, D. J. (2011). A review of methods for estimating anthropogenic heat and moisture emissions in the urban environment. *International Journal of Climatology, 31*(2), 189–199.

Schulman, J., Wolski, F., Dhariwal, P., Radford, A., & Klimov, O. (2017). Proximal policy optimization algorithms. *arXiv preprint arXiv:1707.06347.*

Tordeux, A., Chraibi, M., & Seyfried, A. (2016). Collision-free speed model for pedestrian dynamics. In *Traffic and Granular Flow '15* (pp. 225–232). Springer. (Model implemented in the JuPedSim framework, https://www.jupedsim.org.)

Weidmann, U. (1993). *Transporttechnik der Fussgänger* (Schriftenreihe des IVT Nr. 90). ETH Zürich.

---

*Manuscript prepared as a systems-and-engineering documentation of the U-Shade / HeatGuard / FestCOOL codebase. Where the running implementation diverges from the project specification, the divergence is documented in the text rather than reconciled silently, in keeping with the system's own provenance discipline.*




