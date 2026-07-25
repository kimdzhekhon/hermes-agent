# Deploy Hermes Agent on OCI (Always Free) with a pinned model + public dashboard

This documents a minimal setup that:

- Runs `hermes-agent` on an Oracle Cloud Infrastructure (OCI) Always Free VM
- Pins the model to a single OpenRouter model (`openai/gpt-oss-120b`) — no fallback/MoA
- Exposes `hermes dashboard` publicly through a Cloudflare Tunnel, protected by Cloudflare Access with email one-time-PIN (2FA-equivalent)

## 1. Infrastructure

- OCI Always Free instance, shape `VM.Standard.E2.1.Micro` (x86, 1 OCPU / 1GB) — chosen over `VM.Standard.A1.Flex` because Ampere (A1) capacity is frequently exhausted in busy regions (`Out of host capacity`).
- Ubuntu 24.04 image.
- Security list: inbound TCP/22 (SSH) open to `0.0.0.0/0`. Dashboard port (9119) is **not** opened — it's only reachable through the Cloudflare Tunnel (outbound-only from the VM), so no inbound rule is needed for it.

## 2. Install hermes-agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
```

## 3. Pin the model to a single OpenRouter model

No fallback, no MoA — just one model:

```bash
echo "OPENROUTER_API_KEY=sk-or-..." >> ~/.hermes/.env
chmod 600 ~/.hermes/.env

hermes model set --model openai/gpt-oss-120b --provider openrouter
hermes status   # confirm Provider: OpenRouter, Model: openai/gpt-oss-120b
```

Sanity check with a one-shot prompt:

```bash
hermes -z "1+1은? 한 단어로만."
```

## 4. Dashboard as a systemd service (loopback only)

`hermes dashboard` binds to `127.0.0.1:9119` — never bind it to `0.0.0.0` directly; the tunnel is the only way in.

`/etc/systemd/system/hermes-dashboard.service`:

```ini
[Unit]
Description=Hermes Agent Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
Environment=PATH=/home/ubuntu/.local/bin:/usr/bin:/bin
ExecStart=/home/ubuntu/.local/bin/hermes dashboard --host 127.0.0.1 --port 9119 --no-open
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-dashboard
```

First boot runs `npm ci` to build the web UI — it takes a few minutes before port 9119 starts listening.

## 5. Cloudflare Tunnel (no inbound port needed)

Create the tunnel and point it at the local dashboard port (via Cloudflare API or `cloudflared tunnel create` + a config file with the same effect):

```json
{
  "ingress": [
    { "hostname": "hermes.<yourdomain>.com", "service": "http://localhost:9119" },
    { "service": "http_status:404" }
  ]
}
```

Add a proxied CNAME `hermes` → `<tunnel-id>.cfargotunnel.com` in the zone, then install `cloudflared` as a service on the VM using the tunnel's run token:

```bash
sudo cloudflared service install <TUNNEL_TOKEN>
sudo systemctl status cloudflared
```

## 6. Cloudflare Access — email OTP as the 2FA layer

`hermes-agent`'s own dashboard auth only supports a static username/password (`HERMES_DASHBOARD_BASIC_AUTH_*` env vars) — no built-in TOTP/2FA. Instead of patching the app, put Cloudflare Access in front of the tunnel hostname and let Access's built-in one-time-PIN email login act as the second factor:

- Cloudflare Zero Trust (Free plan, up to 50 users) on the account that owns the domain's zone.
- An Access **self-hosted** application for `hermes.<yourdomain>.com`.
- A policy with decision `allow`, `include: [{ email: { email: "you@example.com" } }]`.

With no other identity provider configured, Access falls back to email one-time-PIN automatically — visiting the dashboard hostname first prompts for that email's OTP before ever reaching the hermes-agent process.

## Result

- `hermes.<yourdomain>.com` → Cloudflare Access (email OTP) → Cloudflare Tunnel → `127.0.0.1:9119` on the OCI VM → hermes dashboard, backed by a single pinned model (`openai/gpt-oss-120b` via OpenRouter).
- No inbound ports open on the VM other than SSH.
