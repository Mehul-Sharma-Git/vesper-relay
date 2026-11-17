# Setting up Vesper Relay (draft)

> Draft written before v1.0. Commands marked **(v1.0)** don't exist yet; they are built by
> the plan tasks named next to them. P5-T6 turns this file into `docs/SETUP.md` and tests
> every command on a fresh Mac account.

Vesper is one engine with several doors. You install the engine once, give it a sandbox
and at least one AI, then use whichever door suits you.

## 1. What you need

| Need | Notes |
| --- | --- |
| A Mac (Apple Silicon or Intel) | Linux works the same way with Docker Engine or Podman. Windows: use WSL2 (later) |
| Python 3.11 or newer | macOS's built-in Python is older. Install with `brew install python@3.12`, or let `uv` manage it |
| Git | `xcode-select --install` or `brew install git` |
| One AI | Any one of: Claude Code, Codex CLI, Gemini CLI (for automatic runs), or any AI app that supports MCP connectors (for the connector door). One is enough |
| A sandbox | Docker Desktop, Colima, or Podman (section 3) |

## 2. Install Vesper (pick one)

| Way | Commands | Best for |
| --- | --- | --- |
| Claude Code plugin **(v1.0, P5-T2)** | In Claude Code: `/plugin marketplace add Mehul-Sharma-Git/vesper-relay`, then `/plugin install vesper-relay@<marketplace name>` | Claude Code users; updates with one command |
| Python tool **(v1.0, P5-T2)** | `uv tool install git+https://github.com/Mehul-Sharma-Git/vesper-relay` (or `pipx install …`), then `vesper install-skill --for <assistant>` | Terminal use, other assistants |
| From source (works today) | `git clone https://github.com/Mehul-Sharma-Git/vesper-relay && cd vesper-relay && python3 -B vesper.py install --for both` | Developing Vesper itself |

## 3. Give Vesper a sandbox

Vesper's AI workers write and run code you haven't read yet. The sandbox keeps them away
from your files, keys and network. Pick one:

| Option | Install | Notes |
| --- | --- | --- |
| Docker Desktop | Download from docker.com, open it once | Easiest; free for personal use |
| Colima | `brew install colima docker` then `colima start --cpu 4 --memory 8` | Free and lightweight; no Desktop app |
| Podman | `brew install podman` then `podman machine init && podman machine start` | Free; no background service on Linux |

The sandbox image (several GB: Python, Go, Node, browsers, AI CLIs) is pulled by
`vesper setup` **(v1.0, P5-T2)**; until then it is built locally **(P1-T9)**.

## 4. Run the setup wizard **(v1.0, P1-T11)**

```sh
vesper setup
```

It asks:

1. **Which AI(s)?** It lists the AI CLIs it finds. One is enough. Choose which brain does
   each job, or accept the defaults (one AI for everything).
2. **Sandbox:** Docker, Colima or Podman; it checks the one you pick is running.
3. **Logins for automatic runs** (only for the AIs you chose):

   | AI | What you run once | Why |
   | --- | --- | --- |
   | Claude Code | `claude setup-token` | The Mac keeps your normal login in Keychain, which the sandbox can't reach |
   | Codex CLI | `codex login` (sign in with ChatGPT) or an API key | Confirm the file location at P1-T8 |
   | Gemini CLI | Its login or API key | Confirm at P1-T8 |

   Secrets go into your Keychain or `~/.config/vesper/secrets.env` (readable only by you),
   never into the config file.
4. **Plan-usage reserve:** how much of your AI plan Vesper must leave for you (default 25%).
5. **How you approve things:** a macOS dialog (default), or a terminal prompt.

It writes `~/.config/vesper/config.toml` and finishes by running `vesper doctor`.

## 5. Check everything **(v1.0, P1-T11)**

```sh
vesper doctor
```

Checks Python, config, sandbox, image architecture, each AI CLI and its flags, and each
login. Every failure comes with the command that fixes it.

## 6. Start using Vesper

| Door | How to start | Notes |
| --- | --- | --- |
| Skill in an AI coding assistant | Open a project folder (empty for a new site, or an existing repo) and type `/vesper-relay <what you want>` in Claude Code, or `$vesper-relay` in Codex | Supervised by default: your assistant does the work, Vesper checks and reviews |
| Command line | `vesper start --mode build --idea "…"`, then `vesper --project RUN review`, `approve`, `run`, `export` | Seeds such as `--seed vite-app` arrive in P4-T8 |
| Connector in an AI app **(v1.0, P5-T1)** | Claude Code: `claude mcp add vesper -- vesper mcp`. Other apps: add a local MCP server whose command is `vesper mcp` | Lets any MCP-capable AI app start and follow runs |
| See plans and designs **(v1.0, P5-T2)** | `vesper --project RUN open` | Opens plans, wireframes and check results in your browser |

Approvals always come to **you**: a dialog or prompt the AI can't answer for you
**(P2-T2)**. Vesper never approves a plan, applies a patch or accepts a risk on its own.

## 7. Updating and removing

| Task | How |
| --- | --- |
| Update (plugin) | `/plugin marketplace update <name>`, or enable auto-update in `/plugin` |
| Update (uv) | `uv tool upgrade vesper-relay` |
| Update the sandbox image | `vesper setup --update-image` **(v1.0)** |
| Remove | Uninstall the plugin or `uv tool uninstall vesper-relay`; delete `~/.config/vesper/` and `~/.local/state/vesper-relay/`; remove the image with `docker image rm` |

## 8. Later: Vesper as a service (after v1.0)

Running Vesper on a server (for phone access, timers and notifications) needs a small server
that can run containers, such as a VPS, or a cloud sandbox provider. Free app-hosting tiers
like Render and Vercel can't run Vesper's sandbox. A separate guide will cover this.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "Cannot connect to the Docker daemon" | Docker Desktop or Colima not running | Open Docker Desktop, or `colima start` |
| Automatic run fails at login | Sandbox token missing or expired | Run that AI's login step from section 4 again |
| A run pauses with `paused_for_limits` | Your plan reserve would be crossed | Wait for the reset time shown, then `run` again |
| `doctor` says an AI CLI's flags changed | The CLI updated | Update Vesper; if still failing, Vesper's repair loop opens a fix for you to merge |
