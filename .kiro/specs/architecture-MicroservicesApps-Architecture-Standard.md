# MicroservicesApps: Architecture Standard for Independent Microservices with One Combined Frontend

## Architecture Overview

- This document is the mandatory category-level architecture authority for every `MicroservicesApps` application. Its rules are normative and must be followed without deviation.
- The AI must obtain explicit approval from the authorized user before proceeding past each required approval gate.
- Approval must be recorded in the canonical decision log with the approved artifact, user identity, date, and decision status. If explicit approval is absent, the AI must stop and must not continue, infer approval, or generate dependent artifacts.
- This document defines reusable category architecture. It is not an application-specific HLD or LLD. Application-specific decisions are documented separately after the PRD and before implementation tasks.
- The required application artifact order is: PRD -> application-specific HLD -> application-specific LLD/Implementation Design -> implementation tasks -> implementation artifacts. This standard governs the architecture boundaries used by those artifacts.
- `MicroservicesApps` applications are managed within **AppHub**. Each application contains **one combined frontend** and **multiple independent backend microservices**.
- Each microservice has its own repository, database, deployment boundary, and four logical backend layers:

1. **Infrastructure:** repositories and data access.
2. **Core:** domain entities, validation, and business rules.
3. **Application:** service coordination and DTO <-> Model mapping.
4. **WebAPI:** HTTP endpoints, controllers, and API presentation.

- The physical folders map to these logical layers as follows: `Infrastructure` to data access, `Core` to the domain, `Application` to coordination and transformation, and `WebAPI` to HTTP presentation. Service logic and DTO mapping remain together in the Application layer because both are application-level concerns.
- Each microservice is autonomous: it is independently developed, deployed, scaled, updated, and owned. Microservices do not share internal domain models. They communicate only through explicit external contracts using approved APIs or messaging mechanisms such as REST, gRPC, GraphQL, WebSockets, Kafka, or RabbitMQ.
- The combined frontend provides one user experience and communicates with the backend services through their approved contracts. It may aggregate microservice responses and scales separately from the backend microservices.
- The architecture is technology-agnostic. Microservices may use different languages, IDEs, frameworks, or databases when project-level contracts and operational compatibility are preserved. Repository and mapping boundaries shield application logic from database-specific details.
- The design supports adding microservices without changing existing microservices when their contracts remain compatible. It enables independent evolution, discrete deployment, and clear ownership. Business rules remain in the Core layer rather than leaking into the frontend or database concerns.

## Physical vs Logical Naming Convention

Physical folder names remain generic and consistent. Logical namespaces, packages, and module paths identify their application context. Backend microservices include both the application name and microservice name; the combined frontend includes the application name and `Frontend`. Logical names do not change the physical folder names.

### Backend Microservice Naming

Physical folders use generic layer names and do not include the application or microservice name:

- `Infrastructure/`
- `Core/`
- `Application/`
- `WebAPI/`

Logical namespaces or packages identify the application, the microservice, the logical layer, and the internal subfolder. This prevents naming conflicts between independently developed microservices:

- C#: `namespace ShopApp.AuthService.Infrastructure.Data`
- Java: `package shopapp.authservice.core.entities`
- Python: `shopapp.authservice.core.entities`
- TypeScript: `@shopapp/auth-service/core`

**Backend formula:**

```text
{AppName}.{MicroserviceName}.{FolderName}.{SubFolder}
```

**Backend example:** `ShopApp.AuthService.Infrastructure.Data` for `AuthDbContext.cs` in `Infrastructure/Data/`.

### Combined Frontend Naming

Each `MicroservicesApps` application has one combined frontend. Its physical folder is generic:

- `Frontend/`

Service-specific API clients are frontend modules under `{FrontendModulePath}`. They communicate with backend services only through approved external contracts and do not contain backend internal domain models. 

The frontend's logical namespaces, packages, or module paths identify the application and the frontend module path. They do not use a microservice name as their root identity because the frontend belongs to the complete application:

- `ShopApp.Frontend.Components.Auth`
- `ShopApp.Frontend.ApiClients.Products`
- `ShopApp.Frontend.State`
- `ShopApp.Frontend.Shared`

**Frontend formula:**

```text
{AppName}.Frontend.{FrontendModulePath}
```

**Frontend example:** `ShopApp.Frontend.ApiClients.Products` for a Products API-client module in `Frontend/ApiClients/Products/` within the combined frontend repository.

## Physical Tiers vs Logical Layers

- **Physical tiers** describe where the system runs, such as database servers, application servers, and client devices. **Logical layers** describe how the code is organized inside each backend microservice.
- The four backend logical layers - `Infrastructure`, `Core`, `Application`, and `WebAPI` - belong to each independent microservice. In the default deployment model, these layers are deployed together on the microservice’s **Application Tier**, while the microservice’s database runs on its **Data Tier** and the combined frontend runs on the **Client Tier**.
- Physical deployment may later use servers, virtual machines, containers, or other compatible infrastructure without changing the logical layer boundaries.

### Enterprise Architecture: Physical to Logical Mapping

The following table maps each physical tier to the component it runs or stores and its logical responsibility.

| Physical tier 	| Runs or stores 						| Logical responsibility 											|
|-----------------------|---------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| **Data Tier** 	| The database owned by the microservice 			| Persistent data storage; database details are accessed through the Infrastructure layer. 			|
| **Application Tier** 	| One independent backend microservice 				| Infrastructure, Core, Application, and WebAPI layers deployed as one service boundary. 			|
| **Client Tier** 	| The one combined frontend in a browser or client device 	| Presents the user experience and communicates with backend services through approved DTO/API contracts. 	|

Within the backend microservice, the logical responsibilities are:

- **Infrastructure:** repositories and database access.
- **Core:** entities, validation, and business rules.
- **Application:** service coordination, DTO mapping, and application workflows.
- **WebAPI:** HTTP endpoints, security boundaries, and external API presentation.

The combined frontend is outside the backend microservice boundaries. It may organize its own pages, components, state, and service-specific API clients, but it does not use the microservices internal domain models.

## Internal Flow (Within Microservice Boundary)

The internal flow defines the responsibility order between the database and the four logical layers of one microservice. The arrows show responsibility and data progression across layer boundaries; they do not prescribe specific method calls or framework implementations.

**Read flow:**

```text
Database -> Infrastructure -> Core -> Application -> WebAPI
```

The database provides persistent data. Infrastructure retrieves it, Core applies domain rules, Application coordinates the use case and maps the result to a DTO, and WebAPI returns the approved external contract.

**Write flow:**

```text
WebAPI -> Application -> Core -> Infrastructure -> Database
```

WebAPI receives the approved external contract. Application coordinates the use case, Core applies domain rules, Infrastructure persists the result, and the database stores it.

The combined frontend communicates with WebAPI through approved API contracts. It remains outside the microservice internal layer boundary and never uses the microservice's internal domain models.

### Internal Flow Rules

- **Validation:** Core enforces domain rules; Application validates use-case and workflow conditions.
- **Mapping:** Convert internal domain data to DTOs only when crossing an external API or microservice boundary.
- **Persistence mapping:** Infrastructure isolates database schema details from Core and Application logic.

### Example Internal Flow

The exact domain entity, endpoint, database technology, and mapping library are defined by the individual microservice implementation, not by this high-level standard.

A generic write operation follows this sequence:

```text
Frontend request -> WebAPI contract -> Application workflow -> Core rules -> Infrastructure persistence -> Database
```

A generic read operation follows this sequence:

```text
Database -> Infrastructure retrieval -> Core data -> Application mapping -> WebAPI contract -> Frontend response
```

### Cross-Cutting Concerns & Resilience

The following concerns apply across the microservice layers and deployment boundary:

- **Observability:** structured logs, correlation identifiers, metrics, tracing, and health/readiness checks.
- **Performance:** caching is generated only when the approved application plan defines its scope, expiration, and invalidation rules.
- **Resilience:** when a downstream dependency is used, the approved dependency design MUST define timeouts, bounded retries with backoff, circuit breaking, and bulkhead isolation according to the dependency's failure modes and approved operational requirements.
- **Security:** authentication, authorization, input protection, rate limiting, and secure handling of sensitive data remain explicit boundary concerns.

These concerns must not move domain rules into the frontend, database, or infrastructure configuration. Their implementation is defined by the approved service technology and by `D:\Zp\AppHub\Governing-Standards\MicroservicesApps\MicroservicesApps-Coding-Skills-Army-Operational-Context.md`.

### Communication Summary

| Boundary 				| Contract or data form 		| Architectural rule 												|
|---------------------------------------|---------------------------------------|---------------------------------------------------------------------------------------------------------------|
| **Combined frontend -> WebAPI** 	| DTO/API contract 			| External communication uses an explicit versioned contract. 							|
| **WebAPI -> Application** 		| DTO or command/query contract 	| Presentation remains separate from application workflow logic. 						|
| **Application -> Core** 		| Domain model or domain command 	| Internal service logic may use domain types within the same microservice boundary. 				|
| **Core -> Infrastructure** 		| Repository or persistence abstraction | Core does not depend on database-specific schema details. 							|
| **Microservice -> Microservice** 	| API contract or integration event 	| Services communicate only through explicit external contracts; internal domain models are never shared. 	|

**DTO and model rule:** Use DTOs or equivalent contracts at frontend, API, gateway, event, and microservice boundaries. Use domain models inside the microservice where the layers share the same internal boundary.
**Transaction rule:** A microservice owns and commits its local transaction. Cross-microservice workflows use explicit coordination, compensating actions, and eventual consistency when required; no distributed transaction is assumed by default.
**Reliability rule:** Commands that may be retried must define idempotency behavior. Frontend optimism must never be treated as confirmation until the backend contract reports an accepted result.

## Single Microservice Folder Structure

Each backend microservice has its own autonomous repository. The repository contains its planning information, tests, and the four approved logical layer folders.

The four layer folders, `planning/`, and `tests/` are mandatory. Inner folders beneath the layers and test scopes beneath `tests/` are created only when the approved service plan explicitly requires them; otherwise they are omitted.

```text
[MicroserviceName]/
|
|-- planning/
|
|-- Infrastructure/
|   |-- Data/                    (database access and persistence configuration)
|   `-- Repositories/            (repository implementations)
|
|-- Core/
|   |-- Entities/                (domain entities and business rules)
|   |-- ValueObjects/            (optional)
|   |-- Events/                  (optional)
|   `-- Interfaces/              (optional domain contracts)
|
|-- Application/
|   |-- Services/                (use-case coordination)
|   |-- DTOs/                    (external request and response contracts)
|   |-- Mappings/                (DTO-to-domain transformations)
|   `-- Validators/              (optional application validation)
|
|-- WebAPI/
|   |-- Controllers/             (HTTP endpoints)
|   |-- Middleware/              (cross-cutting API concerns)
|   `-- Extensions/              (service registration and configuration)
|
`-- tests/
    |-- unit/
    |-- integration/
    |-- contract/                (optional)
    `-- e2e/                     (optional)
```

The layer responsibilities are:

- **Infrastructure:** repositories, persistence access, database configuration, and migrations when explicitly required by the approved service plan.
- **Core:** domain entities, value objects, domain rules, domain events, and domain-level contracts when defined by the approved service plan.
- **Application:** use-case coordination, DTOs, mapping, application validation, and workflow logic.
- **WebAPI:** HTTP endpoints, request and response presentation, authentication and authorization integration, health endpoints, and API middleware.

- The `planning/` folder contains the approved service-specific planning documents. The `tests/` folder contains the service test suites and may contain unit, integration, contract, and end-to-end tests only when those test scopes are defined in the approved service plan.
- Each microservice owns its database and persistence boundary, but the database does not have to be a physical folder in the repository. A local database file may be used only when the approved development environment plan explicitly selects it; otherwise the declared database service is used.
- The combined frontend is not placed inside an individual microservice repository. It belongs to the application-level frontend boundary and communicates with microservices through approved external contracts.
- Internal subfolders and source filenames are defined by the approved service plan before generation. They must remain consistent with the four logical layers and must not create dependencies that violate the approved layer boundaries.

## External Flow (Outside Microservice Boundary)

The one combined frontend communicates with the backend microservices only through approved external contracts. It never accesses a microservice database or internal domain model directly.

**Frontend to backend:**

```text
Combined Frontend -> API Entry Point -> Microservice WebAPI
```

The API Entry Point may be a gateway or an approved direct API route, according to the application deployment plan. The combined frontend may aggregate responses from multiple services to provide one user experience. Real-time features may use a bidirectional channel when required by the product.

**Microservice to microservice:**

- **Synchronous communication:** Use an approved request/response API when an immediate result is required.
- **Asynchronous communication:** Use an approved message or event contract for background workflows and loose coupling.
- **Contract rule:** Services communicate through versioned APIs or integration events; they never share internal domain models or database schemas.

### External Communication Rules

- Use the approved API Entry Point for combined-frontend access to backend services.
- Use synchronous APIs for immediate request/response operations.
- Use asynchronous messages or events for background workflows and cross-service propagation.
- Select REST, gRPC, GraphQL, WebSockets, or a message broker during project planning according to the approved contract and operational requirements.

### API Versioning Strategy

- Every external API and integration event has an explicit contract version. The project must define the versioning mechanism, compatibility period, deprecation notice, and sunset date before a contract is changed.
- Contract changes MUST preserve backward compatibility. If backward compatibility cannot be preserved, the change MUST use a new contract version and a controlled migration path for the combined frontend and dependent microservices.

### Example System Flow

A generic multi-service workflow may follow this pattern:

```text
Combined Frontend
    -> API Entry Point
    -> Order Service
    -> Inventory Service check
    -> Order-created integration event
    -> Payment and Shipping services process independently
    -> Status events return through approved contracts
    -> Combined Frontend displays the unified result
```

The exact communication technology, service names, event names, and deployment products are defined by the approved project plan rather than by this Architecture Standard.

## AppHub Folder Structure

`AppHub` is the logical catalog for all application categories. This Architecture Standard defines the `MicroservicesApps` category in detail. The other categories are included as application slots. Their architecture standards are approved future dependencies and are not current inputs to this `MicroservicesApps` standard.

```text
AppHub/
|
|-- MicroservicesApps/
|   `-- [AppName]/
|       |-- frontend-repository/                 one combined frontend
|       `-- microservice-repositories/
|           |-- [MicroserviceName-1]/             independent repository
|           |-- [MicroserviceName-2]/             independent repository
|           |-- [MicroserviceName-3]/             independent repository
|           `-- ...
|
|-- WebApps/
|   |-- [AppName]/                               defined by the future WebApps Architecture Standard
|   `-- ...
|
|-- DesktopApps/
|   |-- [AppName]/                               defined by the future DesktopApps Architecture Standard
|   `-- ...
|
`-- MobileApps/
    |-- [AppName]/                               defined by the future MobileApps Architecture Standard
    `-- ...
```

This tree is an AppHub catalog representation, not a monorepo requirement. Each listed microservice repository remains autonomous, owns its own database and deployment boundary, and follows the approved single-microservice structure. The `MicroservicesApps` frontend repository is independent and provides the one combined user experience for its application.

The future WebApps, DesktopApps, and MobileApps architecture standards are approved future dependencies. They do not exist yet, are not required inputs for validating this document, and will be created under their respective `D:\Zp\AppHub\Governing-Standards\<Category>\` folders when those categories are designed.

The application-level relationships are:

- One `MicroservicesApps/[AppName]` contains one combined frontend repository.
- One `MicroservicesApps/[AppName]` may contain two or more independent microservice repositories.
- Each microservice repository contains its own `Infrastructure`, `Core`, `Application`, `WebAPI`, planning, and test structure.
- The combined frontend communicates with microservices through approved external contracts and may aggregate their responses.
- No repository shares internal domain models or database schemas with another repository.
- `WebApps`, `DesktopApps`, and `MobileApps` are catalog categories only in this document; their internal structures will be defined separately.

The exact repository names, service count, application planning files, deployment locations, and technology choices are defined by the approved project plan.

## Implementation Roadmap: From Approved Application Artifacts to Running Application

This roadmap defines the mandatory high-level order for converting an approved application definition into a wired, verified, and reproducible `MicroservicesApps` application.

In this standard, `implementation artifacts` are the source code, tests, configuration, contracts, validation evidence, and other approved implementation outputs produced from the implementation tasks. Approved test-driven development (TDD) cycles may order tests before, alongside, or after implementation code within this stage, but no implementation artifact may be produced before the required task gate.

The application-specific artifact order is:

```text
Application-specific PRD (Product Requirements Document)
-> application-specific HLD (High-Level Design)
-> application-specific LLD (Low-Level Design)/Implementation Design
-> implementation tasks
-> implementation artifacts
```

This Architecture Standard governs the architecture boundaries used by those application-specific artifacts. It is not a substitute for the application-specific PRD, HLD, LLD/Implementation Design, or implementation tasks. Detailed skill names, templates, file counts, and technology-specific generation steps belong in `D:\Zp\AppHub\Governing-Standards\MicroservicesApps\microservicesApps-coding-skills-registry.md` and its skills.

### High-Level Workflow

1. **Application-specific PRD:** Create and approve the application-specific Product Requirements Document. It defines the application scope, users, capabilities, and acceptance criteria. The HLD cannot begin until the PRD is approved.
2. **Application-specific HLD:** Create and approve the application-specific High-Level Design using this Architecture Standard. It defines the application topology, service boundaries, data ownership, external contracts, integration events, combined-frontend contract map, and deployment assumptions. The LLD/Implementation Design cannot begin until the HLD is approved.
3. **Application-specific LLD/Implementation Design:** Create and approve the application-specific Low-Level Design/Implementation Design. It translates the HLD into service-level designs, exact contracts, repository and folder decisions, persistence details, frontend module decisions, validation requirements, and implementation traceability. Implementation tasks cannot begin until this artifact is approved.
4. **Implementation tasks:** Derive and approve small, atomic, ordered implementation tasks from the approved LLD/Implementation Design. No implementation artifact may be produced until the required tasks are approved.
5. **Per-microservice implementation artifacts and validation:** Execute the approved tasks for each microservice. Produce the required source code, tests, configuration, contracts, and validation evidence through the approved implementation method, including approved TDD cycles. Generate its four logical layers, configure its persistence boundary, expose its health/API contract, and validate the service before continuing.
6. **Contract and service gates:** Verify every service repository, database boundary, API contract, integration contract, and required health endpoint. A failed prerequisite blocks dependent work; no stage may be skipped.
7. **One combined frontend:** Generate the application frontend once, only after all required backend service contracts pass. The frontend reaches backend services only through approved external contracts.
8. **Whole-system wiring and verification:** Start the services and frontend, verify health responses, exercise representative read and write flows, verify contract compatibility, and confirm that the frontend reaches the backend services.
9. **Reproducibility and packaging:** Rebuild the same canonical inputs twice, compare the complete generated output byte-for-byte, record the verification evidence, and package the independent repositories and combined frontend.

### Required Gates and Evidence

- **Artifact-order gate:** The approved application-specific PRD MUST exist before HLD work begins; the approved HLD MUST exist before LLD/Implementation Design work begins; the approved LLD/Implementation Design MUST exist before implementation tasks begin; approved implementation tasks MUST exist before implementation artifacts are produced. Approved TDD cycles may order tests and implementation code within the implementation-artifact stage.
- **Sequential gates:** A failed prerequisite blocks every dependent stage; skipping to a later stage is not allowed.
- **Canonical inputs:** The same approved PRD, HLD, LLD/Implementation Design, implementation tasks, contracts, templates, pinned tool versions, and configuration inputs are used for every run.
- **Stable output:** Generated paths, file ordering, formatting, serialization, and package ordering are deterministic. Timestamps, random identifiers, and environment-specific values are excluded or normalized.
- **Service evidence:** Each microservice has an independently verifiable repository, database boundary, API contract, and health endpoint.
- **Frontend evidence:** The one combined frontend uses the approved service contracts and successfully reaches the required backend services.
- **System evidence:** Representative end-to-end flows pass across the frontend, API boundary, microservices, and persistence boundaries.
- **Reproducibility evidence:** Two independent builds from identical canonical inputs MUST produce byte-identical output. A byte difference is permitted only when an approved reproducibility record declares its rule ID, exact allowed pattern or value, reason, and verification method before generation; any undeclared or unverified byte difference is a failure.

### Output Boundary

The final `MicroservicesApps` output consists of one application-level combined frontend and multiple independent microservice repositories. Each repository remains autonomous, while the complete application is verified as one wired system. The detailed skill execution order and per-service artifacts are governed by `D:\Zp\AppHub\Governing-Standards\MicroservicesApps\microservicesApps-coding-skills-registry.md`, not by this Architecture Standard.

## Key Takeaways for Developers

This section summarizes rules defined in this Architecture Standard. It does not introduce additional requirements.

### Layer Responsibilities

- **Infrastructure:** owns repositories, persistence access, database configuration, and migrations when defined by the approved service plan.
- **Core:** owns domain entities, value objects, domain rules, domain events, and domain-level contracts within the microservice boundary.
- **Application:** coordinates use cases, workflows, validation, and DTO mapping.
- **WebAPI:** exposes approved external contracts and API boundaries.

### Data and Contract Boundaries

- Database details are isolated behind Infrastructure and do not define Core or Application logic.
- Internal domain models are used only within a microservice boundary.
- DTOs or equivalent contracts are used at frontend, API, gateway, event, and microservice boundaries.
- Microservices share contracts or integration events, never internal implementation classes or database schemas.
- External contracts define the accepted input and returned output.

### Service Autonomy and Security

- Each microservice owns its repository, database boundary, deployment boundary, and exposed contracts.
- Each microservice owns and controls its data and exposed contracts.
- Compatible external contracts isolate the frontend from internal persistence and application changes.
- Authentication, authorization, input protection, and sensitive-data handling remain explicit boundary concerns.

### Configuration and Frontend Principles

- The one combined frontend may be organized into independent feature modules and service-specific API clients.
- The combined frontend communicates with backend microservices only through approved external contracts and does not contain their internal domain models.

### Deterministic Delivery

- Implementation follows the approved artifact order: application-specific PRD -> application-specific HLD -> application-specific LLD/Implementation Design -> implementation tasks -> implementation artifacts, followed by the approved registry gates.
- Generated repositories, contracts, frontend, and system wiring are verified before packaging.
- Identical canonical inputs MUST produce byte-identical output in two independent runs. A byte difference is permitted only when an approved reproducibility record declares its rule ID, exact allowed pattern or value, reason, and verification method before generation; any undeclared or unverified byte difference is a failure.
