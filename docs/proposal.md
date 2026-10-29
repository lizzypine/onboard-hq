# Final Project Proposal

ICS 603  
Lizzy Pine

## Project Goal

A web app that helps community health center staff track new healthcare providers' onboarding tasks, update their progress, and see if they're on track for their first day of work.

## Intended User and Problem

The intended users are community health center managers and administrative staff involved in onboarding new employees.

The problem: Onboarding information is spread across departments such as HR and credentialing. Updates arrive through emails, messages, and conversations, making it difficult to identify outstanding requirements and next actions. A shared application would centralize this information and help authorized users track progress.

## Example Input

A staff member selects fictional provider Dr. Kekoa Ejemplo and enters this synthetic update:

> Kekoa's Hawaii dental license was received. His drug screening is scheduled for October 22. Insurance credentialing has been submitted, but approval is pending. His NED license is still outstanding.

The LLM proposes:

| Requirement | Suggested Status |
| --- | --- |
| Hawaii dental license | Received |
| Drug screening | Scheduled - Oct. 22 |
| Insurance credentialing | Submitted; awaiting approval |
| State NED license | Outstanding |

The user reviews and approves or corrects the suggestions before saving.

## Sample Input Set

Synthetic sample inputs:

| Input | Expected Result |
| --- | --- |
| "Hawaii dental license received." | License: Received |
| "Drug screen scheduled for Oct. 22." | Screening: Scheduled, Oct. 22 |
| "Credentialing was submitted." | Credentialing: Submitted |
| "Still waiting on his NED license." | NED license: Outstanding |
| "Offer letter signed and license received." | Two proposed changes |
| "Drug screen scheduled, date unknown." | Scheduled; flag missing date |

## Expected Result and Value

The application will display each provider's requirements, statuses, deadlines, and proposed start date in one place. Managers should be able to identify outstanding items without contacting multiple departments. I will evaluate this improvement by checking whether the dashboard accurately reflects approved updates in synthetic scenarios.

## Big-Picture Sketch

![Big-picture sketch of the provider onboarding application](proposal-assets/big-picture-sketch.png)

## Workflow or Component Sketch

![Workflow or component sketch of the provider onboarding application](proposal-assets/workflow-component-sketch.png)

## Data Source and Access

The prototype will use manually created, synthetic data modeled after the general onboarding workflow at a local community health center. No real employees’ sensitive data will be used. My contact, a health center manager, will help validate the workflow and sample scenarios.

## Up to Three Core Features

1. **Centralized Onboarding Tracker:** View provider records, requirements, statuses, deadlines, and proposed start dates.
2. **Status and Deadline Monitoring:** Identify completed, pending, outstanding, and overdue requirements using application logic.
3. **LLM-Assisted Status Update Processing:** Extract proposed changes from free-text updates, with human approval required before saving.

## LLM Role

The LLM will interpret free-text updates using the provider's current requirements and statuses. It will return proposed requirement changes, dates, and supporting text, while flagging any ambiguities.

The first model-connected feature will send the selected synthetic provider's context and original update from the page to the model and display structured suggestions. The model will extract stated date components; plain Python will resolve incomplete dates. Suggestions will not change checklist statuses.

The application will use Pydantic AI with a model identifier supplied through `LLM_MODEL` and an OpenAI-compatible gateway supplied through `LLM_API_GATEWAY`. Its token will come from `LLM_API_TOKEN`. Configuration values will be read from the environment; credentials will not be included in the page or model prompt.

Model failures will produce a visible error rather than fixed placeholder suggestions. Automated tests will use `TestModel` with real model requests disabled.

## Data Use

The application will look up the selected provider's record and applicable onboarding requirements before processing an update. It will compare proposed changes with existing requirements and statuses. For example, an update mentioning a NED license should not automatically create a new requirement if that requirement is not associated with the provider type.

For the first model-connected feature, provider context will come from the existing synthetic page fixture, without retrieval or a database. Valid suggestions will remain visible alongside warnings for unknown or non-applicable requirements. If no actionable suggestions remain after filtering, the application will report insufficient information and leave the checklist unchanged.

### Incomplete Dates

For a date with a month and day but no year, infer the most recent valid occurrence on or before the provider's proposed start date. For a day alone, such as "on the 18th," infer the most recent valid occurrence of that day on or before the proposed start date. For example, a January 15, 2027 start implies October 22, 2026 for "October 22," and December 18, 2026 for "on the 18th."

Use actual calendar dates when resolving incomplete dates. Preserve fully specified valid dates as stated. When there is no proposed start date, leave incomplete dates unset and warn. Missing, invalid, or unsupported date wording will not be replaced with a guessed date; show a warning when a date is needed or a date mention cannot be resolved. Do not use today's date as a fallback reference.

Inferred dates will show the original wording, the inferred date, an explanation referencing the proposed start date, and an indication that user approval is required.

## Saved Records

The database will persist the following linked records:

- **Providers:** Identity, provider type, and proposed start date.
- **New-Hire Requirements:** Statuses and deadlines associated with each provider.
- **Updates:** Original free-text messages associated with each provider.
- **LLM Suggestions:** Proposed changes generated from each update.
- **Review Decisions:** Approvals, corrections, and rejections associated with each suggestion.

Each provider can have multiple requirements and updates, and each update can generate multiple suggestions. All records will remain available after restarting the application.

Persistence remains part of the eventual application. The first model-connected feature will not save providers, updates, suggestions, or date confirmations; refreshing the page will reset its temporary state.

## Searchable Text

Saved administrative notes will provide text that could be searched by meaning. For example, a manager might search for "credentialing delays" or "providers waiting on professional licenses" to find relevant historical updates.

Semantic search and retrieval-augmented generation (RAG) are outside the first model-connected feature.

## Human Review

Users will see the original update alongside proposed changes and supporting text. They can approve, correct, or reject each suggestion. Only approved changes will update requirement statuses. Original messages and review decisions will be retained.

The first model-connected feature will include an editable date field and a Confirm date button for each inferred date. Confirmation will apply only to that suggested date in the current page, without approving a status change or saving a record. Editing a date will clear its confirmation, and submitting another update will reset confirmations. General suggestion approval, correction, rejection, and applying checklist status changes remain outside this feature.

## One Failure Case

Input: "Everything looks good. We should be okay for November 1."

This is a failure case because no specific requirement is identified, the application should report insufficient information and leave existing statuses unchanged.

## Three Acceptance Criteria

1. **Successful extraction and approval:** Given an outstanding Hawaii dental license, when the user enters "We received his Hawaii dental license," then the application proposes Received and applies it only after approval.
2. **Multiple requirements:** Given drug-screening and credentialing requirements, when the user enters "Drug screen scheduled for October 22 and credentialing submitted," then the application proposes two independently reviewable changes.
3. **Ambiguous input:** Given an update without a specific requirement status, when the user enters "Everything looks good," then the application reports insufficient information and preserves existing statuses.

## Outside Version One

The initial prototype will exclude:

- Processing of updates sent by forwarded email
- Integration of document uploads
- Automated reminders
- Real employee records

## Open Questions

### Project decisions

- Which provider types and requirements should be included?
- What statuses and deadline rules apply?
- Valid suggestions will be shown alongside warnings for unknown or non-applicable requirements; no applicable suggestions will produce an insufficient-information response.

### Technical questions

- Use Pydantic AI structured output through the configured OpenAI-compatible gateway; the model identifier is deployment configuration supplied through `LLM_MODEL`.
- How should semantic search work?
- How should the application be deployed?

## Next Investigation

The biggest uncertainty is how to model onboarding requirements and statuses accurately while keeping the prototype small enough to complete.

I will review a typical provider onboarding workflow with my contact to identify the most important requirements, their possible statuses, and how they differ by provider type. I will also ask the manager to evaluate several synthetic HR/credentialing updates to determine whether they reflect realistic communications.

Based on that feedback, I may limit version one to one provider type (e.g., dentists) and a small set of common requirements. The investigation will also help determine whether the synthetic updates provide enough detail for reliable LLM extraction.
