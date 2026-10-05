# Universal Agentic Test Case Generation Framework

## 1. Executive Summary

This document outlines the **Universal Agentic Test Case Generation Framework** based on the architecture originally designed for Model-in-the-Loop (MiL) Automotive Systems. It details how the core paradigm—**combining LLM-driven reasoning with deterministic software execution**—can be generalized to generate, execute, and verify tests for any software domain, including Web Applications, REST/GraphQL APIs, Embedded Systems, and Enterprise Microservices.

---

## 2. Core Architectural Philosophy

The fundamental design principle governing the platform is:

> **"LLMs for creativity, reasoning, and synthesis; Deterministic code for truth, execution, and verification."**

```text
               Engineering Data / Specifications / Requirements
                                      │
                                      ▼
                        LLM Reasoning & Synthesis
              (Logic Decompilation, Strategy, Scenario Planning)
                                      │
                                      ▼
                         Universal IR (Intermediate Representation)
                                      │
                                      ▼
                     Deterministic Engineering & Build Gates
              (Signal Mapping, Bounds Check, Reachability, Syntax)
                                      │
                                      ▼
                        Executable Test Synthesis & Oracles
                                      │
                                      ▼
                     Isolated Execution & Runtime Auditing
                                      │
                                      ▼
                       Quality, Coverage & Deliverables
```

---

## 3. The 6 Universal Questions (Mental Model)

Regardless of the target software stack, the platform systematically answers six core engineering questions:

| # | Question | Component Responsible | Purpose |
|---|---|---|---|
| **1** | **What should the system do?** | Requirements Interrogator (Agent 0) | Detects missing `ELSE` paths, ambiguities, and ungrounded parameters. |
| **2** | **What does the target software contain?** | Extractor & Decompiler | Converts specifications into structured logical rules and interface tables. |
| **3** | **Do we have enough information to test it?** | Readiness Gate & Gap Resolver | Performs pure-deterministic checks for syntax, reachability, and bounds completeness. |
| **4** | **What tests should we create?** | Strategist & Architect | Synthesizes coverage-driven test plans, timelines, payloads, and scenarios. |
| **5** | **Are the tests and expected results correct?** | Critic, Programmer & Auditor | Builds deterministic expected-result Oracles, runs isolated tests, and audits runtime logs. |
| **6** | **Did we achieve sufficient verification?** | Quality Analysis & Coverage Scorer | Measures code/branch/MC-DC coverage and packages final engineering deliverables. |

---

## 4. Adaptability Across Software Domains

While the original platform targets Automotive Simulink models, replacing domain-specific parsers, interface resolvers, and test runners allows adaptation to any software layer:

```text
                                  ┌───────────────────────────┐
                                  │   Target Software Domain  │
                                  └─────────────┬─────────────┘
                                                │
         ┌──────────────────────┬───────────────┴───────────────┬──────────────────────┐
         ▼                      ▼                               ▼                      ▼
┌──────────────────┐  ┌──────────────────┐             ┌──────────────────┐  ┌──────────────────┐
│   Automotive /   │  │   Web Apps &     │             │   REST / GraphQL │  │   Embedded C/C++ │
│   Simulink (MiL) │  │   Frontend UI    │             │   Microservices  │  │   Systems        │
└────────┬─────────┘  └────────┬─────────┘             └────────┬─────────┘  └────────┬─────────┘
         │                      │                               │                      │
         ▼                      ▼                               ▼                      ▼
┌──────────────────┐  ┌──────────────────┐             ┌──────────────────┐  ┌──────────────────┐
│ SLDD / FMI XML / │  │ Figma / DOM /    │             │ OpenAPI Specs /  │  │ Header Files /   │
│ Parameters.m     │  │ User Stories     │             │ JSON Schemas     │  │ AUTOSAR ARXML    │
└────────┬─────────┘  └────────┬─────────┘             └────────┬─────────┘  └────────┬─────────┘
         │                      │                               │                      │
         ▼                      ▼                               ▼                      ▼
┌──────────────────┐  ┌──────────────────┐             ┌──────────────────┐  ┌──────────────────┐
│ Simulink Test    │  │ Playwright /     │             │ Pytest / REST    │  │ GoogleTest /     │
│ Manager Excel    │  │ Cypress Specs    │             │ Assured / Postman│  │ Unity / QEMU     │
└──────────────────┘  └──────────────────┘             └──────────────────┘  └──────────────────┘
```

### Domain Mapping Comparison Table

| Feature | Automotive MiL | Web Applications | REST / GraphQL APIs | Embedded C/C++ Systems |
|---|---|---|---|---|
| **Input Metadata** | FMI `modelDescription.xml`, `.sldd`, `Parameters.m` | Figma specs, DOM structure, User Stories | OpenAPI/Swagger, Postman collections, JSON Schemas | Header `.h` files, AUTOSAR ARXML, Doxygen |
| **Interface Unit** | Signals, Enums, Parameters, Calibration Values | Page Objects, Locators, UI Events, Routes | Endpoints, HTTP Methods, Headers, Request Payloads | Functions, Structs, Hardware Registers, Interrupts |
| **Execution Engine** | Discrete-time Simulator / Python LogicModule | Playwright / Cypress / Selenium | Pytest (`requests`), REST Assured, Newman | GoogleTest, CUnity, QEMU Emulators, HIL Rigs |
| **Test Deliverable** | Simulink Test Manager Excel, Coverage JSON | TypeScript / Cypress Test Suites | Pytest API Test Suites, Postman JSON | C/C++ Unit Test files, JUnit XML |
| **Coverage Metric** | Decision, Condition, MC/DC Coverage | UI Component & Route Coverage | Endpoint, HTTP Status, & Branch Coverage | Statement, Branch, & Statement Coverage |

---

## 5. Domain Adaptation Workflow (e.g., REST API Testing)

Below is an example of adapting the pipeline to test a **REST Microservice**:

1. **Requirements Interrogation:**
   * Reads PRD / Jira tickets and OpenAPI specs.
   * Identifies missing 4xx status codes, missing auth constraints, or ungrounded body parameters.
2. **Schema & Endpoint Mapping:**
   * Extracts routes (`POST /api/v1/orders`), headers (`Authorization: Bearer`), request schemas, and response invariants.
3. **Universal IR Generation:**
   * Normalizes requirements into: `Endpoint + Auth Precondition + Request Payload → Expected HTTP Status + Response Schema Invariants`.
4. **Strategy & Scenario Planning:**
   * Generates scenarios for **Nominal Flow (200 OK)**, **Invalid Payload (400 Bad Request)**, **Unauthorized Access (401/403)**, and **Boundary Value Testing**.
5. **Deterministic Oracle & Execution:**
   * Generates Pytest test functions with static JSON schema assertion logic.
   * Executes HTTP requests against a staging container in isolated worker threads.
6. **Coverage & Quality Audit:**
   * Audits HTTP response times, logs, and measures endpoint and code branch coverage via `pytest-cov`.

---

## 7. Key Engineering Challenges & Mitigations

When moving from deterministic discrete-time systems (like Simulink) to general software systems, three key challenges must be handled:

| Challenge | Impact on Testing | Architectural Solution |
|---|---|---|
| **Asynchrony & Latency** | Non-deterministic timing in Web/API calls | Implement explicit wait conditions, dynamic polling assertions, and dynamic timeouts in test scripts. |
| **Stateful Persistence** | Tests altering database state | Enforce isolated test database containers with automated setup/teardown seed fixtures. |
| **Third-Party Side Effects** | External service dependency failures (e.g., Stripe, Twilio) | Automatically generate mock servers (WireMock, MSW) based on OpenAPI dependencies during Phase 1. |

---

## 8. Conclusion

The **Agentic Test Generation Framework** is a universal software testing paradigm. By decoupling **Requirement Reasoning (LLMs)** from **Domain Execution (Deterministic Engines)**, it provides a scalable, hallucination-free foundation for automating software verification across any technology stack.
