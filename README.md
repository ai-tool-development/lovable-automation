# Lovable Remix Automation

> **⚠️ EXPERIMENTAL PROOF OF CONCEPT**
>
> This project is an experimental exploration of browser automation for Lovable.dev. It is not production-ready and may break at any time if Lovable changes their UI. Use at your own risk.

Headless browser automation for creating Lovable project remixes.

## Overview

This is an **experimental proof of concept** demonstrating programmatic remix creation for Lovable projects using headless browser automation. Since Lovable doesn't expose a public remix API, this uses Playwright to automate the UI flow.

**Experimental Features:**
- Headless email+password authentication
- UI-based remix via Playwright
- Session persistence for reuse
- Safety mechanisms (rate limiting, circuit breaker, idempotency)
- Docker-ready for server deployment

**Limitations:**
- Relies on UI selectors that may change without notice
- Not officially supported by Lovable
- May trigger rate limiting or account restrictions
- Session tokens may expire unexpectedly

## Quick Start

### Local Development

```bash
# 1. Setup
cd lovable-automation
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# 2. Configure
cp .env.example .env
# Edit .env with your credentials

# 3. Authenticate
python cli.py auth

# 4. Create a remix
python cli.py ui-remix <project_id> -y
```

### Docker

```bash
# Build
docker build -t lovable-automation .

# Run with environment variables
docker run --rm \
  -e LOVABLE_EMAIL=your-email@example.com \
  -e LOVABLE_PASSWORD=your-password \
  -v $(pwd)/session_state:/app/session_state \
  lovable-automation python cli.py auth

# Create remix
docker run --rm \
  -e LOVABLE_EMAIL=your-email@example.com \
  -e LOVABLE_PASSWORD=your-password \
  -v $(pwd)/session_state:/app/session_state \
  lovable-automation python cli.py ui-remix <project_id> -y
```

Or use docker-compose:

```bash
# Copy and edit .env
cp .env.example .env

# Auth
docker-compose run lovable-automation python cli.py auth

# Remix
docker-compose run lovable-automation python cli.py ui-remix <project_id> -y
```

## Commands

### `auth` - Authentication

```bash
python cli.py auth              # Login with email/password
python cli.py auth --force      # Clear session, re-authenticate
python cli.py auth --show       # Display full bearer token
```

### `ui-remix` - Create Remix (Recommended)

```bash
python cli.py ui-remix <project_id>        # Remix with confirmation
python cli.py ui-remix <project_id> -y     # Skip confirmation
python cli.py ui-remix <project_id> --no-history  # Without edit history
python cli.py ui-remix <project_id> --json # Output JSON result
```

### `status` - Safety Status

```bash
python cli.py status            # Show current safety state
python cli.py status --verbose  # Include request log
```

### `reset` - Reset Safety State

```bash
python cli.py reset             # Show warning
python cli.py reset --confirm   # Actually reset
```

## Configuration

### Environment Variables (.env)

```bash
# Authentication (required)
LOVABLE_EMAIL=your-email@example.com
LOVABLE_PASSWORD=your-password

# Project Configuration (optional)
LOVABLE_PROJECT_ID=your-default-project-id

# Browser Automation Settings
HEADLESS=true    # Set to true for server/Docker
SLOW_MO=50       # Milliseconds between actions
```

## Safety Features

| Protection | Description | Default |
|------------|-------------|---------|
| **Rate Limiting** | Minimum delay between requests | 2 seconds |
| **Hourly Limit** | Max requests per hour | 60 |
| **Daily Remix Limit** | Max remixes per day | 20 |
| **Circuit Breaker** | Auto-stop after failures | 3 consecutive |
| **Idempotency** | Prevents duplicate remixes | Per session |
| **Confirmation** | Requires user consent | Unless `--yes` |

## Architecture

```
lovable-automation/
├── cli.py          # Command-line interface
├── ui_remix.py     # UI automation (main remix logic)
├── auth.py         # Email/password login flow
├── safety.py       # Safety mechanisms
├── config.py       # Configuration management
├── api.py          # API client (limited use)
├── Dockerfile      # Docker image definition
├── docker-compose.yml
├── .env            # Credentials (gitignored)
└── session_state/  # Persisted state
    ├── lovable_session.json
    ├── bearer_token.txt
    └── safety_state.json
```

## How It Works

### Authentication Flow

1. Navigate to lovable.dev/login
2. Enter email, click Continue
3. Enter password, click Log In
4. Capture bearer token from network requests
5. Save session (cookies + token) for reuse

### Remix Flow

1. **Pre-check**: Rate limit, daily limit, circuit breaker
2. **Idempotency**: Check if already remixed
3. **Confirmation**: Prompt user (unless `--yes`)
4. **Navigate**: Go to project page
5. **Click**: Menu → "Remix this project"
6. **Confirm**: Handle dialog, click Remix
7. **Wait**: Detect redirect to new project URL
8. **Record**: Log result, update safety state

## Troubleshooting

### "Rate limit: wait X.Xs"
Normal - the tool enforces minimum delays between actions.

### "Circuit breaker active"
Too many failures. Wait 15 minutes or: `python cli.py reset --confirm`

### "Already remixed"
Project was remixed in current session. Reset to allow re-remix.

### "Timeout waiting for remix"
The remix may have succeeded but detection failed. Check Lovable dashboard.

### Session expired
Re-authenticate: `python cli.py auth --force`

## Programmatic Usage

```python
from ui_remix import ui_remix

result = ui_remix(
    project_id="your-project-id",
    include_history=True,
    skip_confirmation=True,  # For automated workflows
)

if result and result.success:
    print(f"New project: {result.new_project_url}")
else:
    print(f"Error: {result.error if result else 'Blocked'}")
```

## Testing Status

### ✅ Verified (Local macOS)

| Component | Status | Notes |
|-----------|--------|-------|
| Email+password login | ✅ Tested | Two-step flow (email → continue → password → login) |
| Headless mode | ✅ Tested | `HEADLESS=true` works |
| Session persistence | ✅ Tested | Cookies + token saved/reused |
| Token capture | ✅ Tested | Captured from network requests |
| UI remix flow | ✅ Tested | Menu → "Remix this project" → dialog → confirm |
| Redirect detection | ✅ Tested | `wait_for_url()` with regex |
| Safety dashboard | ✅ Tested | Rate limits, circuit breaker visible |
| CLI commands | ✅ Tested | `auth`, `ui-remix`, `status` |

### ⚠️ Needs Verification

| Component | Status | Notes |
|-----------|--------|-------|
| Docker build | ⚠️ Untested | Dockerfile created but not built |
| Docker run | ⚠️ Untested | Commands documented but not executed |
| docker-compose | ⚠️ Untested | Config created but not tested |
| Linux server | ⚠️ Untested | Only tested on macOS |
| Session expiry | ⚠️ Untested | Long-term token validity unknown |
| EC2/cloud IPs | ⚠️ Untested | Datacenter IPs may trigger challenges |
| Concurrent runs | ⚠️ Untested | Multiple simultaneous remixes |

### Recommended Verification Steps

```bash
# 1. Build Docker image
docker build -t lovable-automation .

# 2. Test auth
docker run --rm \
  -e LOVABLE_EMAIL=your-email \
  -e LOVABLE_PASSWORD=your-password \
  -v lovable_session:/app/session_state \
  lovable-automation auth

# 3. Test remix
docker run --rm \
  -e LOVABLE_EMAIL=your-email \
  -e LOVABLE_PASSWORD=your-password \
  -v lovable_session:/app/session_state \
  lovable-automation ui-remix <project_id> -y

# 4. Verify session reuse (should not re-login)
docker run --rm \
  -v lovable_session:/app/session_state \
  lovable-automation status
```

## Disclaimer

This is an **unofficial, experimental project** not affiliated with or endorsed by Lovable. It may violate Lovable's terms of service. The authors are not responsible for any consequences of using this tool, including but not limited to account suspension or data loss.
