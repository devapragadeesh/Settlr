# Meta: What Actually Wins This Format

## The event
Razorpay AI Buildathon is a student-only hiring funnel for an AI Builder Intern role, 75,000 rupees per month, 6 or 12 months, in-person Bangalore. Graduation years 2027 to 2029. No resume screening, no aptitude test, no group discussion.

Four steps: pick a track, build something real, show your work as a public repo plus a five minute pitch video plus the architecture, then a panel interview.

The pitch is a recorded video, not a live demo. This removes live-demo risk and makes demo craft a production problem.

The application form is a five-field lead capture collecting email, name, college, graduation year and September availability. It does not collect a repo or a track, so the build is gated later in the funnel.

## Why this is a hiring loop, not a demo day
The evaluator decides whether to put this person on a team for 12 months. Downside risk dominates upside: one unjustifiable architectural decision in the panel is a no-hire. The repo is evaluated asynchronously and unaccompanied, so it must be self-explanatory.

Razorpay's reported interview loop includes an agentic coding round alongside machine coding, high-level design and culture. Candidates report Razorpay probes trade-off justification and failure modes, not just the happy path.

## The published answer key
Razorpay's Slash engineering post states a three-pillar repo readiness model at 80 percent: Context, meaning how well a repo describes itself to an agent; Testing, meaning how safely an agent can validate its own work; and CI/CD. It stresses scoped auditable permissions, agent output passing the same checks as any other change, and measured adoption metrics.

Translated: the repo should be agent-readable, test-covered, CI-green, with scoped tool permissions and a metrics table.

Every track's bar says the same thing in five dialects: audit trail, measured metrics, honest exception list, graceful failure, bounded actions. They are asking for evidence that the builder knows how to know whether their system works.

Show one failure handled gracefully means the video must contain a deliberate scripted failure segment where the system detects, refuses, escalates and logs rather than hallucinating success. Place it at roughly minute three and a half as the emotional peak.

## Track crowding, inferred not measured
Track 01 Agentic Commerce is predicted highest crowding because it is hype-adjacent and the official MCP server makes the happy path trivially reachable.
Track 05 Open Track is high crowding as the default for pet projects.
Track 03 Revenue Recovery is medium.
Track 02 Risk Manager is low, because Razorpay themselves say it surfaces the risk and ML minded builders the others miss.
Track 04 Finance Controller is lowest, because reconciliation is unglamorous and invisible to students.

## Anti-patterns that lose
Breadth as insurance, meaning four half-loops instead of one closed loop. Cherry-picked results. No held-out set or evaluating on data you tuned against. Hiding the exception list. Framework-shaped answers where a framework name substitutes for a reason. Unbounded agent authority with no approval gate on irreversible actions. A repo the reviewer cannot run. A polished video over a working system. Repo and video mismatch.
