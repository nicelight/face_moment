---
description: Реестр доступных скиллов (когда применять) в этом репозитории.
status: active
---
# Skills

## Installed
<!-- BEGIN DEVRAILS INSTALLED SKILLS -->

| Skill | Codex `.agents` | Claude `.claude` |
| --- | --- | --- |
| <code>add-tests</code> | yes | yes |
| <code>architecture-review</code> | yes | yes |
| <code>autonomous</code> | yes | yes |
| <code>autopilot</code> | yes | yes |
| <code>brainstorm</code> | yes | yes |
| <code>brief</code> | yes | yes |
| <code>constitution</code> | yes | yes |
| <code>context-manifest</code> | yes | yes |
| <code>creator-vibe</code> | yes | yes |
| <code>debug</code> | yes | yes |
| <code>discuss</code> | yes | yes |
| <code>exe</code> | yes | yes |
| <code>feature-doctor</code> | yes | yes |
| <code>feature-to-tasks</code> | yes | yes |
| <code>fill</code> | yes | yes |
| <code>find-skills</code> | yes | yes |
| <code>foundation-to-tasks</code> | yes | yes |
| <code>kiss-architect</code> | yes | yes |
| <code>map-codebase</code> | yes | yes |
| <code>mb-doctor</code> | yes | yes |
| <code>mb-garden</code> | yes | yes |
| <code>mb-init</code> | yes | yes |
| <code>mb-sync</code> | yes | yes |
| <code>prd-to-features</code> | yes | yes |
| <code>red-verify</code> | yes | yes |
| <code>review-feat-plan</code> | yes | yes |
| <code>review-tasks-plan</code> | yes | yes |
| <code>spec-auto</code> | yes | yes |
| <code>spec-design</code> | yes | yes |
| <code>spec-init</code> | yes | yes |
| <code>spec-redesign</code> | yes | yes |
| <code>start</code> | yes | yes |
| <code>tech-debt</code> | yes | yes |
| <code>technical-premortem</code> | yes | yes |
| <code>verify</code> | yes | yes |
| <code>write-prd</code> | yes | yes |

Используй guidance ниже только для skill, отмеченного как `yes` в активной runtime surface.

<!-- END DEVRAILS INSTALLED SKILLS -->

## When to use
- Bootstrap skeleton: /mb-init
- Scenario routing: /cold-start
- Discovery artifacts: /brainstorm for raw ideas, then /brief; clear concepts may start at /brief
- Project principles: /constitution after /brief or existing PRD context, before /write-prd only when project_principles is not ratified|partial
- PRD → MB: /write-prd, lightweight /spec-init, /prd-to-features, /spec-design, /foundation-to-tasks when required, close the FT-000 foundation gate, then /feature-to-tasks
- SDD design: /spec-init for lightweight route-map preflight, /spec-design for mandatory adaptive global backbone and foundation decision after /prd-to-features, foundation tasking inside /foundation-to-tasks, foundation gate closure before product tasking, initial and repair feature-level design/task reconciliation inside /feature-to-tasks, /spec-auto for autonomous design
- Map codebase: /map-codebase
- Execution: /exe
- Verification (UAT): /verify
- Semantic adversarial verification: /red-verify
- Autonomous run: /autonomous, /autopilot
- Readiness doctor: /mb-doctor
- Review: /review-feat-plan, /review-tasks-plan
- Maintenance: /mb-garden
- Harness: mb-harness
