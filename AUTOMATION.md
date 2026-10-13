# Running SPEKY from scripts and AI agents

SPEKY was built for a person at a terminal: it asks questions as it goes. This page
covers the two ways to run it unattended:

1. **No-prompt mode.** Every question is answered from a flag, a file or its default.
2. **Host mode.** The agent running SPEKY (Claude Code, Cursor, Codex…) acts as
   SPEKY's model, so SPEKY makes no LLM calls of its own.

Everything here is also in `speky --help` and `speky <command> --help`.

## No-prompt mode

| Option | Effect |
|---|---|
| `-y`, `--yes` | Yes to every confirmation. Other questions take their default |
| `--answer "QUESTION=VALUE"` | Answer any question whose text contains `QUESTION` (case-insensitive). Repeatable |
| `--answers FILE` | Many answers at once, from a JSON or YAML file |
| `--non-interactive`, `--no-input` | Never read the keyboard: use `--answer`, else the default |

These are global options: they work before or after the command
(`speky -y spec X` and `speky spec X -y` are the same).

**Non-interactive mode turns on by itself when stdin is not a terminal.** That
covers CI, cron, pipes, and the shell tools AI agents use. Set
`SPEKY_INTERACTIVE=1` to turn that off.

### How questions get answered

- **Text questions:** the matching `--answer`, else the default. If there's no
  default, an empty answer, which most prompts treat as "skip".
- **Yes/no questions:** the matching `--answer` (`y`/`yes`/`true`/`1` mean yes),
  else yes with `-y`, else the question's own default. `-y` only says yes the first
  time a confirmation is asked. If the same one comes back in a loop ("Add another?"),
  it gets its default, so `-y` never loops forever.
- **Multiple choice:** the matching `--answer`, as the option number or part of its
  text (`--answer "How would you like to proceed=start fresh"`). Choices have no
  default, so an unanswered choice stops the run (see below).
- **Multi-line text and "press Enter" pauses:** the matching `--answer`, else empty
  or skipped.

Every answer chosen without you is printed, so the log shows what was decided:

```
   ↳ How would you like to proceed? → 'No, start fresh' (--answer)
   ↳ Generate implementation plan now? → 'yes' (--yes)
```

### When SPEKY needs an answer

If a choice has no answer, or a question keeps being re-asked, SPEKY exits with
**code 4**. It prints the question, the options, and the flag to add:

```
❓ SPEKY needs an answer it cannot get without a terminal.
   Question: How would you like to proceed?
   Choose one of (number or part of the text):
     1. Yes, I'll place files in the research folder
     2. I'll paste notes directly
     3. No, start fresh
   Re-run the same command with:  --answer "How would you like to proceed=<value>"
```

### Answers file

```yaml
# answers.yaml — keys are matched against question text, like --answer
How would you like to proceed: start fresh
Add to phase: phase-1
Generate implementation plan now: yes
```

When the same question is asked several times (for example, once per item) and each
time needs a different answer, use a list. The entries are used in order:

```yaml
- Your answer: Busy parents doing the weekly shop
- Your answer: Shared list, real-time sync, item check-off
- Your answer: Phones at the store
```

```bash
speky init "A grocery app for families" --answers answers.yaml
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | The command failed |
| 2 | Bad usage (unknown option, missing value) |
| 4 | A question needs an `--answer` (non-interactive mode) |
| 130 | Interrupted |

## Existing projects: `init --from-project`

In a repo that already has code and docs, a person shouldn't have to re-type what
the README already says. `speky init --from-project` reads the project and answers
init's questions itself:

| Init step | Where the answer comes from |
|---|---|
| Product idea | Optional. Taken from the README title and first paragraph |
| Research documents | `README*`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`/`.windsurfrules`, root `*.md`, `docs/`, `design/`, `specs/`, plus the folder structure. A snapshot goes to `.speky/imports/initial_research/` |
| Clarifying questions | The model answers each one from that evidence and names its sources. A question the evidence can't answer is left blank, never invented |
| Tech stack | Read directly from `package.json`, `pyproject.toml`/`requirements.txt`, `go.mod`, `Cargo.toml`, `pubspec.yaml`, `Gemfile`, Maven/Gradle files, Docker/compose, `vercel.json`, `netlify.toml`, `fly.toml` and similar. The analysis fills any gaps |
| "Create specs from research?" | Skipped when unattended, since an existing project has probably built those features already. Add `--answer "Your choice=MVP"` to create them anyway |
| "Import POC code?" | Not asked: the project is the code |

At a terminal you still see every question, with the project's answer as the
default: press Enter to accept, or type over it. Unattended, the project's answers
are used as they are.

It also runs **automatically** when SPEKY is unattended (no terminal, `-y`, or an
agent) in a folder that already has docs or manifests. Agents never get stuck on
"Do you have existing docs?".

```bash
speky init --from-project                 # existing repo, SPEKY's configured model
speky init --from-project --host          # existing repo, the calling agent is the model
speky init --from-project                 # already initialized: refresh the product profile and
                                          # tech stack; specs, stories and phases are kept
```

Host mode suits this best. The agent answering the prompts can read the actual code,
not just the docs, and the prompts tell it to.

## Host mode

In host mode SPEKY doesn't call an LLM. When it needs one, it:

1. writes the full prompt, with SPEKY's context and instructions, to
   `.speky/host/NNN.prompt.md`;
2. prints `⏸️  SPEKY host request NNN — waiting for the agent to answer`;
3. **waits** until the answer is delivered, then continues in the same process.

Because SPEKY waits rather than exiting, nothing is re-run and no files or spec
numbers are created twice. When an answer is used, the prompt and answer move to
`.speky/host/done/`, which keeps a record of every exchange.

Turn it on with `--host`, `SPEKY_MODEL=host`, or `speky config --model host`.

| Command | What it does |
|---|---|
| `speky host status` | List prompts waiting for an answer |
| `speky host show [ID]` | Print a waiting prompt (default: the oldest) |
| `speky host answer ID --file F` | Deliver an answer (or pipe it on stdin) |
| `speky host guide` | Print instructions for your agent |

Requests time out after 30 minutes. To change that, set `timeout` (in seconds) for
the `host` provider in `~/.speky/models.yaml`:

```yaml
providers:
  host:
    timeout: 3600
```

### Using it from Claude Code

Add the agent instructions to your project once:

```bash
speky host guide >> CLAUDE.md
```

Then ask Claude Code something like *"create a SPEKY spec for login using host mode"*.
It will:

1. start `speky spec "Login" --host -y` **in the background**. SPEKY has to keep
   running while Claude Code answers, so a foreground call would just block;
2. watch the output. At each `⏸️  SPEKY host request NNN` it runs
   `speky host show NNN`, writes the answer from what it knows of your codebase,
   and runs `speky host answer NNN --file answer.md`;
3. repeat until the command finishes.

The same loop works with any agent that can run a background process and read its
output.

### Which mode should I use?

| You want | Use |
|---|---|
| SPEKY to run unattended with its own model (CI, scripts) | No-prompt flags, with any provider |
| One agent doing all the thinking, with full codebase context, and no second model to pay for | Host mode |
| The cheapest unattended runs with no API key | `--llm claude-code/sonnet` (your Claude subscription), or host mode |

In host mode SPEKY keeps doing its own job: project memory in `.speky/`, specs,
phases, validation structure, and the IDE rules files. The agent supplies the
reasoning. The two don't overlap, so they don't contradict each other.
