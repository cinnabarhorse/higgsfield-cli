# Higgsfield CLI

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A powerful command-line tool for generating images via [Higgsfield.ai](https://higgsfield.ai)'s API, built through reverse-engineering their web application.

## 🎨 What It Does

Higgsfield CLI (`hf`) lets you generate AI images from your terminal using Higgsfield.ai's free tier. It bypasses Cloudflare protection using TLS fingerprinting and implements the Clerk authentication flow to access generation endpoints directly.

**Key Features:**
- 🔐 Full authentication via Clerk (email/password + device verification)
- 🎯 Direct API access to multiple generation models
- 🚀 Cloudflare bypass using browser TLS impersonation
- 💾 Session persistence (login once, use forever)
- 📊 Credit tracking and usage history
- 🎨 Multiple models: Z-Image, Soul, Flux-2, GPT, and video models
- 🔄 Automatic JWT token refresh

## ✨ Features

- **Simple Text-to-Image:** Generate images from prompts in seconds
- **Multiple Models:** Access Z-Image, Soul (stylized), Flux-2, GPT-based models, and more
- **Video Generation:** Support for image-to-video and text-to-video models
- **Customization:** Control dimensions, aspect ratios, seeds for reproducibility
- **Account Management:** Check credits, view generation history
- **Session Persistence:** Login once, stored securely in `~/.config/hf/`
- **Rich Terminal UI:** Beautiful progress bars and formatted output

## 📋 Prerequisites

- **Python 3.10 or higher**
- **pip** (Python package installer)
- **Higgsfield.ai account** (free tier works)

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/higgsfield-cli.git
cd higgsfield-cli
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

**Or install in development mode:**

```bash
pip install -e .
```

### Dependencies

- **curl_cffi** — HTTP client with browser TLS fingerprinting (bypasses Cloudflare)
- **click** — Command-line interface framework
- **rich** — Beautiful terminal formatting and progress bars

## ⚡ Quick Start

Get up and running in 3 commands:

```bash
# 1. Login to your Higgsfield account
hf login

# 2. Generate your first image
hf generate "a cyberpunk cityscape at night with neon lights"

# 3. Check your remaining credits
hf status
```

## 📖 Usage

### `hf login`

Authenticate with your Higgsfield.ai account.

```bash
hf login
```

**What happens:**
1. You'll be prompted for your email and password
2. **First login:** A 6-digit verification code will be sent to your email
3. Enter the code to verify your device
4. Session is saved to `~/.config/hf/session.json` (secure permissions)
5. Future logins are automatic until session expires (~1 year)

**Example:**
```
$ hf login
Email: your.email@example.com
Password: ********
🔐 Starting login...
📧 Verification code sent to your.email@example.com
Enter the 6-digit code from your email: 123456
✓ Login successful!
```

---

### `hf generate <prompt>`

Generate an image from a text prompt.

**Alias:** `hf gen`

```bash
hf generate "a serene mountain landscape at sunset" [OPTIONS]
```

**Options:**

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--model` | `-m` | `z-image` | Model to use (see Available Models) |
| `--width` | `-w` | `1024` | Image width in pixels |
| `--height` | `-h` | `1024` | Image height in pixels |
| `--aspect-ratio` | `-a` | `1:1` | Aspect ratio (1:1, 16:9, 9:16, 4:3, etc.) |
| `--seed` | `-s` | Random | Random seed for reproducibility |
| `--output` | `-o` | Auto | Output file path (default: `hf_<timestamp>.png`) |

**Examples:**

```bash
# Basic generation (1024x1024, Z-Image model)
hf generate "a cute red panda eating bamboo"

# Custom dimensions and aspect ratio
hf generate "wide cinematic landscape" --width 1920 --height 1080 --aspect-ratio 16:9

# Use a specific seed for reproducibility
hf generate "abstract art" --seed 42

# Save to specific location
hf generate "portrait of a cat" --output ~/Desktop/cat.png

# Use a different model
hf generate "stylized portrait" --model soul
```

---

### `hf models`

List all available image generation models.

```bash
hf models
```

**Output:**
```
┌──────────┬─────────────────┬────────────────────────────────────┐
│ ID       │ Name            │ Description                        │
├──────────┼─────────────────┼────────────────────────────────────┤
│ z-image  │ Z-Image         │ Simple, fast image generation      │
│ soul     │ Soul Standard   │ Stylized generation (style_id)     │
│ flux-2   │ Flux 2          │ Advanced model (input_images)      │
│ gpt      │ GPT Image       │ OpenAI-based generation            │
└──────────┴─────────────────┴────────────────────────────────────┘
```

---

### `hf status`

Show your account information and credit balance.

```bash
hf status
```

**Output:**
```
┌──────────────┬────────────────────────────────────────┐
│ Property     │ Value                                  │
├──────────────┼────────────────────────────────────────┤
│ Email        │ your.email@example.com                 │
│ Session File │ /home/user/.config/hf/session.json     │
│ Credits      │ 8                                      │
│ Plan         │ Free                                   │
└──────────────┴────────────────────────────────────────┘
```

---

### `hf history`

View your recent image generations.

```bash
hf history [--limit N]
```

**Options:**
- `--limit` / `-n` — Number of items to show (default: 10)

**Example:**
```bash
hf history --limit 5
```

**Output:**
```
┌──────────────────┬─────────┬────────────────────────┬───────────┐
│ Created          │ Model   │ Prompt                 │ Status    │
├──────────────────┼─────────┼────────────────────────┼───────────┤
│ 2026-02-13 14:32 │ z-image │ a cute red panda...    │ completed │
│ 2026-02-13 14:15 │ z-image │ cyberpunk cityscape    │ completed │
│ 2026-02-13 13:45 │ soul    │ stylized portrait      │ completed │
└──────────────────┴─────────┴────────────────────────┴───────────┘
```

---

## 🎯 Available Models

Higgsfield CLI supports multiple generation endpoints. **Note:** Some models require additional parameters not yet exposed in the CLI.

### Image Generation Models

| Model ID | Endpoint | Description | Input Requirements | Status |
|----------|----------|-------------|-------------------|--------|
| **z-image** | `/jobs/z-image` | Fast, simple text-to-image | Prompt only | ✅ Fully supported |
| **soul** | `/jobs/text2image-soul` | Stylized generation | Prompt + `style_id` | ⚠️ Needs style_id param |
| **flux-2** | `/jobs/flux-2` | Advanced Flux model | Prompt + `input_images` | ⚠️ Needs input images |
| **gpt** | `/jobs/text2image-gpt` | OpenAI-based generation | Prompt | ✅ Supported |
| **nano-banana-2** | `/jobs/nano-banana-2` | Nano Banana variant | Prompt + `input_images` | ⚠️ Needs input images |
| **nano-banana-2-static** | `/jobs/nano-banana-2-static` | Static variant | Prompt + `input_images` | ⚠️ Needs input images |
| **seedream** | `/jobs/seedream` | Seedream model | Prompt + `input_images` | ⚠️ Needs input images |
| **seedream-v4-5** | `/jobs/seedream-v4-5` | Seedream v4.5 | Prompt + `input_images` + `quality` | ⚠️ Needs input images |
| **openai-hazel** | `/jobs/openai-hazel` | OpenAI Hazel | Prompt | ⚠️ Not tested |

### Video Generation Models

| Model ID | Endpoint | Description | Input Requirements |
|----------|----------|-------------|-------------------|
| **image2video** | `/jobs/image2video` | Convert image to video | Input image |
| **kling** | `/jobs/kling` | Kling video model | Input configuration |
| **veo3** | `/jobs/veo3` | Veo3 video generation | Input configuration |
| **wan2-5-video** | `/jobs/wan2-5-video` | Wan 2.5 video model | Input configuration |
| **minimax-hailuo** | `/jobs/minimax-hailuo` | MiniMax Hailuo | Input configuration |
| **sora2-video** | `/jobs/sora2-video` | Sora 2 video generation | Input configuration |
| **seedance** | `/jobs/seedance` | SeeDance video model | Input configuration |

**Note:** Video models are accessible via the API but require additional parameters not currently exposed in the CLI. Future versions may add full support.

---

## 🔧 How It Works

### Reverse-Engineering Details

Higgsfield CLI works by replicating the web application's authentication and API flows:

#### 1. Clerk Authentication Flow

Higgsfield.ai uses [Clerk](https://clerk.com) for authentication. The login process:

1. **Sign-In Attempt:** `POST /v1/client/sign_ins` with email/password
2. **Device Verification:** On first login, Clerk requires email code verification
3. **Session Creation:** Successful auth returns a session ID and `__client` cookie
4. **Token Refresh:** JWTs expire in ~60 seconds, refreshed via `POST /v1/client/sessions/{sid}/tokens`

**Key Insight:** The `__client` cookie on `.clerk.higgsfield.ai` is long-lived (~1 year). Session persistence uses this cookie + session ID.

#### 2. Cloudflare Bypass via TLS Fingerprinting

Higgsfield's API is protected by Cloudflare, which blocks standard Python HTTP clients (`requests`, `urllib3`, `httpx`) based on TLS fingerprints.

**Solution:** `curl_cffi` library provides browser TLS impersonation:

```python
from curl_cffi import requests

session = requests.Session(impersonate="chrome131")
```

This makes requests indistinguishable from a real Chrome 131 browser at the TLS layer.

**Additional Warmup:** Before API calls, the CLI hits `https://higgsfield.ai` to establish a Cloudflare session.

#### 3. Token Refresh Mechanism

JWT tokens expire quickly (~60 seconds). The client:

1. Loads saved session from `~/.config/hf/session.json`
2. Before each API call, refreshes the JWT via Clerk's token endpoint
3. Uses fresh JWT in `Authorization: Bearer {jwt}` header

#### 4. Job Submission → Polling → Download Pipeline

Image generation is asynchronous:

1. **Submit:** `POST /jobs/{model-endpoint}` with generation parameters
   - Returns job set ID
2. **Poll:** `GET /job-sets/{job_set_id}` every 2 seconds
   - Status progression: `queued` → `in_progress` → `completed`
3. **Download:** Extract CloudFront CDN URL from `jobs[0].results.raw.url`
   - Download image directly to local filesystem

**Token Management During Polling:** JWT is refreshed every 20 poll cycles (~40 seconds) to prevent expiration during long generations.

---

## 💳 Rate Limits & Credits

### Free Plan
- **10 credits per day** (resets at midnight UTC)
- Each generation typically costs **1 credit**
- Credit balance visible via `hf status`

### Credit Costs by Model

| Model | Credits per Generation |
|-------|------------------------|
| Z-Image | 1 |
| Soul | 1 |
| Flux-2 | 1-2 |
| Video models | 2-5 (varies) |

**Note:** Exact credit costs depend on parameters like resolution and batch size. Free tier limits may change.

---

## 🛠️ Troubleshooting

### "Not logged in. Run 'hf login' first."

**Cause:** No saved session or session expired.

**Solution:**
```bash
hf login
```

---

### "Failed to refresh token: 401"

**Cause:** Session expired or invalidated.

**Solution:**
1. Delete old session: `rm ~/.config/hf/session.json`
2. Re-login: `hf login`

---

### Cloudflare Blocks / 403 Errors

**Cause:** TLS fingerprint detection or rate limiting.

**Solution:**
1. Ensure `curl_cffi` is correctly installed with browser impersonation
2. Update impersonation target:
   ```python
   IMPERSONATE = "chrome131"  # Try "safari15_5" or other browsers
   ```
3. Add delays between requests
4. Check if your IP is rate-limited (try different network)

---

### Proxy / Corporate Networks

If you're behind a proxy, set one of:
- `HF_PROXY` (applies to both HTTP + HTTPS)
- `HF_HTTP_PROXY` / `HF_HTTPS_PROXY`
- `HTTP_PROXY` / `HTTPS_PROXY` (or lowercase variants)

**Example:**
```bash
HF_PROXY=http://127.0.0.1:8080 hf status
```

---

### "Verification code sent to..." but no email arrives

**Cause:** Email in spam or Clerk rate limiting.

**Solution:**
1. Check spam/junk folder
2. Wait 60 seconds and try again
3. Verify email address is correct

---

### Generation hangs / times out

**Cause:** API queue delays or network issues.

**Solution:**
1. Free tier may have longer queue times during peak hours
2. Check your internet connection
3. Try again later
4. Increase timeout in code if needed (default: 2 minutes)

---

### Session file permissions error

**Cause:** `~/.config/hf/session.json` has wrong permissions.

**Solution:**
```bash
chmod 600 ~/.config/hf/session.json
```

---

## ⚖️ Legal Disclaimer

**This tool is unofficial and not affiliated with Higgsfield.ai.**

- Built through reverse-engineering the web application's API
- Use at your own risk
- Respect Higgsfield's Terms of Service
- Free tier usage only (paid tier endpoints not tested)
- May break if Higgsfield updates their API or authentication
- Not responsible for account bans or API changes

**Educational Purpose:** This project demonstrates API reverse-engineering, Cloudflare bypass techniques, and OAuth flow implementation. Use responsibly.

---

## 📄 License

MIT License

Copyright (c) 2026 Higgsfield CLI Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- [ ] Add support for `style_id` parameter (Soul models)
- [ ] Implement input image upload for Flux-2, Nano Banana models
- [ ] Add batch generation support
- [ ] Implement video generation commands
- [x] Add proxy support for additional CF bypass
- [ ] Better error messages and retry logic
- [ ] Configuration file for defaults
- [ ] Export history to JSON/CSV

---

## 🔗 Links

- [Higgsfield.ai](https://higgsfield.ai) — Official website
- [curl_cffi Documentation](https://curl-cffi.readthedocs.io/) — TLS impersonation library
- [Clerk Documentation](https://clerk.com/docs) — Authentication platform

---

**Enjoy generating! 🎨**

*If you find this useful, consider starring the repo ⭐*
