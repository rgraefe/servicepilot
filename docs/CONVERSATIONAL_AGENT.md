# Conversational Agent

## Phase 4 scope

Phase 4 defines the ServicePilot conversational architecture as version-controlled
Dialogflow CX playbooks. Phase 5 adds the backend OpenAPI tool while managed
data-store integration still belongs to Phase 7. This separation lets routing,
delegation, safety boundaries, and failure behavior be reviewed before an LLM can
read or mutate business data.

The source of truth is `conversation/catalog.json`. It contains:

- the German agent settings
- global guardrails
- routing precedence
- DefaultService as the entry-point routine playbook
- four task playbooks
- German routing and safety examples for every playbook

`conversation/golden_routes.json` is the Phase 4 routing corpus. The deterministic
`conversation.routing_contract` classifier runs only in CI as an ownership
preflight. Production routing remains generative and is performed by DefaultService.

## Playbook responsibilities

| Playbook | Type | Responsibility |
| --- | --- | --- |
| DefaultService | Routine/default | Greeting, clarification, routing, multi-intent priority |
| KnowledgeSupport | Task | Technical, error-code, manual, warranty, and FAQ questions |
| ServiceTicket | Task | Ticket lookup and confirmation-safe ticket preparation |
| AppointmentManagement | Task | Appointment lookup and confirmation-safe change preparation |
| ComplaintManagement | Task | Complaints, de-escalation, and requests for a human |

DefaultService contains no business workflow. It references all specialists with
Dialogflow's `${PLAYBOOK: name}` syntax. An explicit human request or complaint
has highest precedence, followed by appointment intent, ticket intent, and
technical knowledge intent. For multiple requests, the selected specialist
receives the remaining concerns in the conversation summary.

Every delegation example supplies an explicit preceding-conversation summary to
the specialist and a corresponding execution summary. This is required for
reliable context transfer: an example that only names the target playbook may be
selected by the model without carrying identifiers or the customer's requested
outcome into the child playbook.

## One-time agent creation

Create the agent once in the
[Conversational Agents console](https://conversational-agents.cloud.google.com/):

1. Select project `servicepilot-development`.
2. Select **Create agent** and **Build your own**.
3. Use agent name `ServicePilot`.
4. Use location `europe-west3`.
5. Use time zone `Europe/Berlin`.
6. Use German (`de`) as the immutable default language.
7. Select **Playbook** for **Conversation start** when the option is available.
8. Create the agent and copy its UUID from the agent URL or settings.

Do not choose Flow as the entry point. Phase 6 will add a deterministic flow for
the critical rescheduling write without replacing the default playbook.

Enable the Dialogflow API once:

```powershell
gcloud services enable dialogflow.googleapis.com --project=servicepilot-development
```

## Deploy backend tools and playbooks

Phase 5 requires the private Cloud Run service to use ingress `all` unless an
organization-specific Service Directory path is configured. `all` does not make
the service public: Cloud Run IAM still rejects callers without a valid invoker
identity.

Preview and apply the tool plus least-privilege invoker binding first:

```powershell
./scripts/deploy-conversational-tools.ps1 `
  -ProjectId servicepilot-development `
  -Region europe-west3 `
  -AgentId YOUR_AGENT_UUID `
  -CloudRunServiceName servicepilot-api `
  -WhatIf

./scripts/deploy-conversational-tools.ps1 `
  -ProjectId servicepilot-development `
  -Region europe-west3 `
  -AgentId YOUR_AGENT_UUID `
  -CloudRunServiceName servicepilot-api
```

The script resolves the canonical Cloud Run URL, grants `roles/run.invoker` to
the Google-managed Dialogflow service agent, injects the URL into the OpenAPI
schema in memory, and creates or updates `ServicePilotBackend` with service-agent
ID-token authentication. It creates an immutable tool version only when no
identical schema/authentication version exists. No credential is written to disk.

Then preview the playbook change:

Preview the change:

```powershell
./scripts/deploy-conversational-agent.ps1 `
  -ProjectId servicepilot-development `
  -Region europe-west3 `
  -AgentId YOUR_AGENT_UUID `
  -WhatIf
```

Apply it:

```powershell
./scripts/deploy-conversational-agent.ps1 `
  -ProjectId servicepilot-development `
  -Region europe-west3 `
  -AgentId YOUR_AGENT_UUID
```

The playbook script converges resources by display name. It requires
`ServicePilotBackend` to exist, creates missing specialist and
DefaultService playbooks, updates existing prompts, assigns DefaultService as the
agent's `startPlaybook`, and synchronizes named examples. Dialogflow appends the
repeated `actions` field during an example PATCH, so the script replaces an
existing named example before recreating its ordered actions. It does not create
flows, data stores, service-account keys, or secrets.

## Routing acceptance checks

Run the local contract suite in Docker:

```powershell
docker compose run --rm api pytest tests/conversation
```

Then use the Dialogflow simulator with a new session for each representative case:

| User message | Expected playbook |
| --- | --- |
| `Meine Wärmepumpe zeigt Fehler E37.` | KnowledgeSupport |
| `Wie ist der Stand von Ticket T-4711?` | ServiceTicket |
| `Steht mein Technikertermin morgen noch?` | AppointmentManagement |
| `Ich bin mit dem bisherigen Service sehr unzufrieden.` | ComplaintManagement |
| `Ich möchte jetzt mit einem Mitarbeiter sprechen.` | ComplaintManagement |
| `Meine Anlage zeigt E37 und ich möchte wissen, ob der Techniker morgen kommt.` | AppointmentManagement, retaining E37 context |
| `Ich brauche Hilfe.` | DefaultService asks one clarification question |

In Phase 5, specialists may report canonical read results and explicitly confirmed
ticket creation only after successful tool output. Appointment rescheduling remains
deferred to Phase 6.

## Change workflow

1. Update `conversation/catalog.json`.
2. Add or update golden routes.
3. Run the Docker test suite.
4. Preview and apply the deployment script.
5. Run the simulator acceptance cases.
6. Review Dialogflow validation warnings before promoting a new playbook version.

Google documentation:

- [Playbooks](https://cloud.google.com/dialogflow/cx/docs/concept/playbook)
- [Playbook instructions](https://cloud.google.com/dialogflow/cx/docs/concept/playbook/instruction)
- [Playbook examples](https://cloud.google.com/dialogflow/cx/docs/concept/playbook/example)
- [Conversational Agents console](https://cloud.google.com/dialogflow/cx/docs/concept/console-conversational-agents)
