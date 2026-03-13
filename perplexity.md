
# Perplexity dialogue on improving ilo management

## David's comments
This is mostly for iron-lo but, once we create the skills or MCPs, it would be useful to the other ilos too.

## Conversation

### David
I don't suppose iLO (v5 I think) has an API . And, if does, I don't suppose it offers a connection to the console.
iLO 5 absolutely has an API, but it does not expose the graphical console as a nice, documented API in the same way it exposes power/BIOS/etc. management; the console uses a proprietary KVM protocol that you can tap into but not via standard Redfish/REST calls.

### Perplexity
What APIs iLO 5 offers
iLO 5 implements an HPE “iLO RESTful API” that is Redfish‑conformant, over HTTPS with JSON.

Through this you can do power control, inventory, BIOS and iLO config, logs, virtual media, and more.

The Redfish Manager resource exposes things like GraphicalConsole, CommandShell, VirtualMedia, etc., so you can at least discover what console types are supported (e.g. KVMIP, Oem).
​

Remote console / KVM access
The actual iLO remote console (what you see in the HTML5 console in the web GUI) is not exposed as a documented REST or Redfish streaming API; it’s a separate KVM‑over‑IP protocol behind the scenes.

Older iLO generations used a Java applet; newer ones (including iLO 5) use an HTML5 client that talks to iLO using WebSockets with an internal, mostly undocumented protocol.

There are community reverse‑engineering efforts (e.g. the ilo-protocol Node.js project) that implement the remote console protocol (video stream + keyboard/mouse) over TCP/WebSockets by calling internal endpoints like /json/rc-info and then opening the console port, but this is explicitly not an official API and can break with firmware changes.
​

What you can and can’t do programmatically
You can (officially):

Script all the usual lifecycle bits over Redfish/REST (power, reboot, mount ISO via virtual media, set boot order, configure BIOS/iLO, pull sensors/logs).
​

Discover that a graphical console is available and what connection types are supported.
​

You cannot (officially):

Use the supported Redfish / REST APIs to pull the live framebuffer or send key/mouse events as a first‑class documented API; HPE expects you to use the web GUI or thick client for that.

Rely on the console protocol as stable or supported if you script against the reverse‑engineered WebSocket/TCP protocol.
​

If your end goal is “headless automation” (reboots, PXE/ISO boot, config) iLO 5’s REST/Redfish is solid; if it’s “pipe the console into my own tool,” you’re in unofficial/reverse‑engineered territory. Are you trying to embed the console in a custom dashboard/agent framework, or are you mainly after noninteractive lifecycle automation?

### David
Both goals. I currently have claude code use playwright to manage the ilo and to use the console when necessary.

What are my best options for improving both?

### Perplexity

You can get a lot better than “LLM driving Playwright in the web UI,” but it splits into two tracks: use Redfish/SSH/CLI for lifecycle, and only fall back to browser automation (or a hacked console client) when you truly need pixels.

1. Improve lifecycle automation (power, boot, media, config)
Goal: eliminate Playwright for anything that doesn’t strictly require a framebuffer.

Best options:

Use the iLO 5 Redfish/REST API (or ilorest) for all control-plane actions.

Power on/off/reset, boot source, one-time PXE, virtual media insert/eject, BIOS and iLO config, inventory, logs are all first‑class here.

HPE publishes full Redfish schemas and examples for iLO 5, plus Python snippets you can adapt into your own MCP tools.

Wrap Redfish in a thin, deterministic tool layer:

Write a small Python or Go “iloctl” that exposes opinionated commands (iloctl power cycle, iloctl boot iso, iloctl set-bios), with idempotent behavior and good error codes.

Have Claude Code call that via a tool/MCP instead of driving the browser for these actions.

Use the iLO 5 SSH/text interface where appropriate:

The iLO CLI over SSH has commands like POWER, VM, UID, NMI and VSP that you can script with any SSH library.

This is excellent for “stuck host but still POSTing” workflows and gives you a serial‑style console (VSP) when the OS exposes one.
​

A simple pattern: Claude chooses “API tool” for power/boot/config, only selects “Playwright web UI” when the tools say a feature is missing or return an error.

2. Improve console access options
Here you have three realistic tiers, from most robust to most like what you have today.

a) Prefer serial/text console when possible
Enable serial console (Linux: console=ttyS0,… etc.) and map it to iLO “Virtual Serial Port” (VSP).
​

Then your automation stack can:

SSH to iLO, run VSP, and talk to the OS login over a predictable, line‑oriented stream.

Wrap that in a small daemon that exposes the serial stream over WebSocket or SSE to your own UI, which Claude can also use as a “text console” tool.

This avoids any browser automation or undocumented KVM protocol but still lets you capture boot and OS text.

b) Script the HTML5 console with a dedicated client
HPE doesn’t document the KVM protocol, but community projects have reverse‑engineered enough of it to build non‑browser console clients (e.g., Node.js implementations that speak the WebSocket protocol used by the HTML5 console).

You could:

Run such a client headless alongside your MCP/agent, expose a WebRTC/WebSocket bridge or MJPEG stream that your dashboard and Claude can attach to.

Keep all the fragile “speak iLO’s KVM dialect” code in that one component, instead of spreading Playwright scripts everywhere.

This is still unsupported and can break on firmware updates, but it’s less flaky than teaching an LLM to drive DOM changes in a rich SPA.

c) Keep Playwright, but harden it
If you stick with Playwright as the console fallback, make it as deterministic as possible:

Replace “LLM explores UI” with a fixed library of flows:

open_console(), mount_iso(url), reboot_to_iso(), etc., each implemented as stable selectors and robust wait conditions.

Claude chooses from those flows via tools rather than issuing arbitrary Playwright code.

Handle auth and SSO cleanly:

Use a dedicated service account, avoid CAPTCHAs or client cert prompts, reuse sessions/cookies where iLO allows.

Capture output in a consumable format:

Periodically screenshot or record the console frame and store it, so Claude sees images/logs instead of streaming the live console only via Playwright.

3. How I’d architect it for your stack
Given you’re already wiring Claude Code into your infra, I’d aim for:

Function	Mechanism
Power / reboot	Redfish or ilorest via tool
Boot order / PXE / ISO	Redfish virtual media + boot
BIOS / iLO config	Redfish/ilorest scripts
Text/serial console	iLO SSH + VSP → WebSocket
Pixel console (fallback)	Dedicated KVM client or Playwright wrapper
Claude’s tools would be:

ilo_power_tool (your small API wrapper)

ilo_boot_media_tool

ilo_serial_console_tool (attach, read, write, detach)

ilo_graphical_console_tool (rarely used; either talks to your KVM client or kicks off a known Playwright script)

Once those exist, most of what Playwright is doing today can be removed or isolated into a single “graphical emergency” path.

Would you be up for leaning on a serial console (VSP) as your primary “interactive” path, and keeping graphical console purely as an escape hatch?

Follow-ups

Build iLO Redfish automation script with console fallback
Computer

Python Redfish client library examples for iLO 5

Switch Claude code from Playwright to Redfish API

Handle iLO console KVM-IP access via API

iLO 5 Redfish authentication methods

