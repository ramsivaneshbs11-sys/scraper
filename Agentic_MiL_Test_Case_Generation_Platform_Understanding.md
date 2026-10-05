# Understanding of the Agentic MiL Test Case Generation Platform

## 1. One-Line Understanding

This system takes **automotive engineering requirements and Simulink/model information** and automatically creates, executes, validates, audits, and measures test cases using **multiple AI agents combined with deterministic Python logic**.

## 2. Main Inputs

- Requirements workbook
- FMI `modelDescription.xml`
- Simulink Data Dictionary (`.sldd`)
- MATLAB calibration file (`_Parameters.m`)
- Other engineering templates/data

These describe feature behavior, signals, enums, parameters, calibration values, model interfaces, conditions, thresholds, and expected behavior.

## 3. Overall Flow

```text
Engineering Inputs
        |
        v
Requirements Interrogation
        |
        v
Human Requirements Review
        |
        v
Extraction + Logic Decompilation
        |
        v
Signal / Interface Mapping
        |
        v
Golden Interface Contract
        |
        v
Universal IR
        |
        v
Gap Detection + Readiness Check
        |
        v
Test Strategy
        |
        v
Scenario Planning
        |
        v
Evidence Contracts
        |
        v
Coverage Feasibility
        |
        v
Test Architecture
        |
        v
Plan Validation
        |
        v
Deterministic Oracle Generation
        |
        v
Test Execution
        |
        v
Runtime Audit
        |
        v
Quality Analysis
        |
        v
Final V&V
        |
        v
Coverage Measurement
        |
        v
Final Test Deliverables
```

## 4. Phase 0 — Requirements Interrogation

### Agent 0 — Interrogator

The first agent reads the raw requirements and asks:

> Are these requirements complete, consistent, and testable?

It looks for:

- Missing `ELSE` behavior
- Missing enable conditions
- Missing validity conditions
- Missing thresholds
- Orphaned thresholds
- Multiple writers/conflicting outputs
- Ambiguous conditions
- Incomplete GIVEN/WHEN/THEN logic

It produces:

`Triage_Requirements_Matrix.xlsx`

It also records `agent_0_excel_path` and `agent_0_slot_guesses`.

### Human Requirements Review

An engineer reviews, edits, or approves the findings. The pipeline stays in review until the requirements are approved.

**Important:** The system does not blindly trust the original requirements.

## 5. Phase 1 — Extraction and Mapping

### Agent 1 — Data Miner

Extracts information from engineering documents and creates an initial `system_context`.

### Agent 1.5 — Logic Decompiler

Converts natural-language requirements into structured engineering logic and maps requirements to signals.

Example:

```text
IF vehicle speed > 50
AND feature is enabled
AND steering angle exceeds a threshold
THEN compensation becomes active.
```

Conceptually:

```text
vehicle_speed > 50
        AND
feature_enable == TRUE
        AND
steering_angle > threshold
        |
        v
feature_state = ACTIVE
```

The result is `decompiled_report`.

It uses a heavy-reasoning LLM, persistent per-prompt cache, and the canonical symbol table.

### Human Mapping Review

If a signal mapping is uncertain, the engineer resolves it. If nothing is ambiguous, this step can be skipped.

### Agent 1 — Systems Engineer

Reconciles the extracted information against:

- FMI XML
- Data Dictionary
- `Parameters.m`
- Engineering tools/data

It resolves signals, completes enum tables, checks interfaces, reconciles parameters, and freezes the **Golden Interface Contract**.

The output becomes the initial **Universal IR**.

## 6. Universal IR

The **Universal Intermediate Representation** is the central structured representation of the feature.

Conceptually:

```text
Requirement
    |
    +-- Conditions
    +-- Signals
    +-- Thresholds
    +-- Enums
    +-- States
    +-- Preconditions
    +-- Outputs
    +-- Relationships
```

Instead of every later agent repeatedly reading multiple raw files, downstream agents work from the Universal IR.

## 7. Phase 2 — IR Completion and Gap Closure

### Signal Resolver

Deterministically resolves placeholders such as:

`UNKNOWN_SIGNAL_PLEASE_ADVISE`

using the model dictionary, canonical symbols, and calibration naming conventions.

### Agent 2 — Detective

Checks:

1. Syntax
2. Coverage
3. Bounds
4. Enum validity
5. Preconditions
6. Reachability

For example, if:

`Temperature > threshold -> Cooling ON`

it may ask what the threshold is, whether the comparison is `>` or `>=`, the valid temperature range, how cooling is enabled, whether the state is reachable, and what happens exactly at the threshold.

### Gap Resolver

Tries to answer missing questions from grounded source data. It is capped by `MAX_GAP_RESOLVER_ATTEMPTS`. Truly unresolved information goes to a human.

### Readiness Gate

A **pure-Python buildability check** verifies:

- Reachability
- Unknown placeholders
- Threshold grounding
- Enum validity
- Write graph
- Required information

If blockers remain, it produces:

`Requirements_Readiness_Report.md`

and stops the pipeline unless explicitly bypassed.

## 8. Phase 3 — Strategy, Scenarios, Contracts, Routing

### Agent 3.5 — Strategist

Creates coverage obligations such as:

- Nominal behavior
- Boundary conditions
- Fault injection
- State coverage
- Diagnostic behavior
- Calibration behavior

### Agent 3.6 — Scenario Planner

Groups related obligations into domain-aligned scenarios, for example:

- `Nominal_And_States`
- `Faults_Diagnostics`
- `Calibration_Tuning`

### Agent 3.7 — Evidence Contract Builder

Defines what evidence would prove each requirement.

Example:

```text
Requirement:
Cooling shall activate above 80°C

Controllable:
battery_temperature

Observable:
cooling_request

Calibration:
temperature_threshold

Proof:
temperature crosses threshold
        |
        v
cooling_request becomes TRUE
```

It also defines forbidden direct drives and initializes the coverage ledger.

### Agent 3.8 — Coverage Router

Determines whether an objective should be:

- **KEEP**
- **RELOCATE**
- **DEFER TO HUMAN**

It produces `DEBUG_Feasible_Scenarios.json`.

## 9. Phase 4 — Architect and Critic Loop

### Pop Scenario

Dequeues the next feasible scenario. When the queue is empty, it assembles the master plan and moves to programming.

### Agent 4 — Architect

Creates concrete `TestStrategy` objects containing:

- Stimulus timeline
- Initial conditions
- Input values
- Parameter overrides
- Expected behavior
- Coverage claims
- Design justification

Example:

```text
Initial temperature = 70°C

t=0:
feature_enable = TRUE

t=1:
temperature = 79°C

t=2:
temperature = 81°C

Expected:
cooling_request = TRUE
```

### Agent 4.5 — Plan Validator / Critic

Checks:

- Timeline consistency
- Signal bounds
- Enum validity
- Forbidden direct drives
- Sample-time alignment
- Other engineering constraints

If it fails, the Architect is revisited. The loop is capped by `MAX_ARCHITECT_DEBATE_CYCLES`.

## 10. Phase 5 — Oracle Generation and Execution

### Agent 5 — Programmer

Generates a deterministic Python `LogicModule`.

The LogicModule acts as the expected-value oracle: given inputs and conditions, it calculates what the expected output should be.

It is:

- IR-hash cached
- Deterministic
- Invariant-checked
- Able to fall back to per-requirement block compilation

The sandbox check rejects NaN, infinity, and crashes before trusting the oracle.

### Python Executor

Runs the LogicModule against every test case in isolated multiprocessing.

```text
Test Case
    |
    v
Stimulus
    |
    v
LogicModule
    |
    v
Expected Result
    |
    v
Execution Data
```

If generated code crashes, the Programmer is revisited up to `MAX_EXECUTION_RETRIES`.

### Agent 5.5 — Runtime Auditor

Checks actual execution traces for:

- Correct `t=0` initialization
- Deny-signal masking
- Division-by-zero behavior
- Forbidden patterns
- Other runtime invariants

It has:

- Layer 1: deterministic Python checks
- Layer 2: LLM audit

Failures go to the Remediation Planner, which can create a permanent QA rule in `global_qa_rules`. The loop is capped by `MAX_AUDIT_CYCLES`.

## 11. Phase 6 — Quality, Formatting, V&V and Coverage

### Agent 7 — Quality Analysis

Optional/additive quality layers include:

- Metamorphic invariants
- Multi-oracle agreement
- Mutation adequacy scoring

### Dynamic Formatter

Converts generated tests into the client's **Simulink Test Manager Excel** template and handles array calibrations, enums, and booleans.

### Final V&V Review Panel

Reviews the complete run.

Issues can be routed back to the Architect or Programmer, with a limit controlled by `MAX_VNV_BOUNCES`.

### Agent 8 — Coverage Scorer

Instruments the LogicModule AST and replays the suite to measure:

- Execution coverage
- Decision coverage
- Condition coverage
- MC/DC coverage

It generates:

`DEBUG_Requirements_Coverage.json`

## 12. Core Architectural Principle

The most important principle is:

> **LLM for creativity, deterministic Python for truth.**

LLMs are mainly used for:

- Understanding natural language
- Decompiling logic
- Reasoning about requirements
- Planning scenarios
- Synthesizing test strategies
- Assisting with audits

Deterministic Python is mainly used for:

- Signal resolution
- Validation
- Bounds checking
- Enum checking
- Reachability
- Test execution
- Oracle validation
- Runtime checks
- Coverage measurement

So the architecture is:

```text
             LLM
              |
     Understanding
     Reasoning
     Planning
     Synthesis
              |
              v
        Universal IR
              |
              v
     Deterministic Layer
              |
     +--------+---------+
     |        |         |
  Validate  Execute   Audit
     |        |         |
     +--------+---------+
              |
              v
         Measurements
```

## 13. Human-in-the-Loop

Humans are involved only where the system cannot safely resolve an issue.

Main HITL points:

1. Requirements Review
2. Signal Mapping Review
3. Missing Information / Clarification
4. Untestable Cases

The goal is:

> **Human judgment where necessary, not human busywork.**

## 14. Deterministic Backbone

Important core modules include:

```text
pipeline/core/
```

- `state.py` — master AgentState schema
- `llm_config.py` — LLM configuration, OAuth, retry/backoff and timeout handling
- `symbol_table.py` — canonical engineering vocabulary
- `name_resolver.py` — signal-name resolution
- `name_qualifier.py` — signal qualification
- `contract_extractor.py` — formal guards, bounds and preconditions
- `coverage_ledger.py` — coverage obligation source of truth
- `feasibility.py` — deterministic feasibility checks
- `scenario_index.py` — scenario indexing
- `testcase_cache.py` — stable test hashing
- `oracle_tools.py` — IR hashing, block compilation and invariant checking
- `multi_oracle.py` — multiple-oracle confidence mechanism
- `signal_resolver.py` — deterministic signal placeholder resolution

## 15. Engineering Tools Layer

Important `pipeline/tools/` modules include:

- `file_readers.py` — XML, ARXML, PDF, DOCX, TXT extraction
- `fmi_reconciler.py` — FMI reconciliation
- `dd_reconciler.py` — Data Dictionary reconciliation
- `parameters_m_reader.py` — calibration parameter reading
- `sldd_reader.py` — SLDD reading
- `req_reader.py` — requirements reading
- `interface_contract.py` — Golden Interface Contract
- `ir_graph.py` — dependency/reachability graph
- `stimulus_generator.py` — deterministic stimulus generation
- `simulation_engine.py` — discrete-time simulation
- `code_runner.py` — isolated execution
- `dynamic_formatter.py` — STM Excel output
- `metamorphic.py` — metamorphic checks
- `mutation_adequacy.py` — mutation adequacy
- `physics_validator.py` — physics-related validation
- `knowledge_vault.py`, `lexicon_vault.py`, `vault_io.py` — persistent knowledge/answer caches

## 16. How This Differs From Normal RAG

A normal RAG system is approximately:

```text
Documents
   |
   v
Chunk
   |
   v
Embedding
   |
   v
Vector Search
   |
   v
LLM
   |
   v
Answer
```

This Agentic MiL platform is:

```text
Engineering Data
      |
      v
Requirement Analysis
      |
      v
Logic Decompilation
      |
      v
Signal Reconciliation
      |
      v
Universal IR
      |
      v
Readiness Verification
      |
      v
Test Strategy
      |
      v
Scenario Planning
      |
      v
Test Synthesis
      |
      v
Deterministic Oracle
      |
      v
Simulation
      |
      v
Runtime Audit
      |
      v
V&V
      |
      v
Coverage
      |
      v
Engineering Deliverables
```

Therefore, this is **not simply a RAG chatbot**. RAG/retrieval may be one supporting capability inside a much larger controlled engineering pipeline.

## 17. Simplest Mental Model

The platform answers six major questions:

### 1. What should the system do?

**Requirements + Interrogator**

### 2. What does the actual model contain?

**Data Miner + Decompiler + Systems Engineer**

### 3. Do we have enough information to test it?

**Detective + Gap Resolver + Readiness Gate**

### 4. What tests should we create?

**Strategist + Scenario Planner + Evidence Contract Builder + Architect**

### 5. Are the tests and expected results correct?

**Critic + Programmer + Executor + Auditor**

### 6. Did we achieve sufficient verification?

**Quality Analysis + V&V + Coverage Scorer**

## 18. Final Understanding

This system is best understood as a:

> **Controlled Agentic Automotive Test-Case Generation and Model-in-the-Loop Verification Platform.**

Its goal is not merely to generate test cases.

Its goal is to:

> **Understand engineering requirements, reconcile them with the actual model interface, determine what can be tested, generate executable tests, calculate expected behavior deterministically, execute and audit those tests, measure coverage, and produce an engineering-ready deliverable.**

The key architectural idea is:

> **LLMs provide reasoning and synthesis; deterministic engineering software provides constraints, execution, verification, and measurable truth; humans resolve genuinely ambiguous or missing information.**
