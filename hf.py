#!/usr/bin/env python3
"""
Higgsfield CLI - Generate images (and videos) via Higgsfield.ai API
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import click
from curl_cffi import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# Constants
API_BASE = "https://fnf.higgsfield.ai"
CLERK_BASE = "https://clerk.higgsfield.ai"
WARMUP_URL = "https://higgsfield.ai"
CONFIG_DIR = Path.home() / ".config" / "hf"
SESSION_FILE = CONFIG_DIR / "session.json"
IMPERSONATE = "chrome131"
CLERK_QUERY = {
    "__clerk_api_version": "2025-11-10",
    "_clerk_js_version": "5.127.2",
}


def _configure_session_proxies(session: requests.Session) -> None:
    """
    Optional proxy support.

    Precedence:
      1) HF_PROXY (applies to both http/https)
      2) HF_HTTP_PROXY / HF_HTTPS_PROXY
      3) HTTP_PROXY / HTTPS_PROXY (and lowercase variants)
    """
    proxy_all = (os.environ.get("HF_PROXY") or os.environ.get("hf_proxy") or "").strip()
    if proxy_all:
        session.proxies.update({"http": proxy_all, "https": proxy_all})
        return

    http_proxy = (
        os.environ.get("HF_HTTP_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
        or ""
    ).strip()
    https_proxy = (
        os.environ.get("HF_HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or ""
    ).strip()

    # If only one is set, use it for both; most proxy endpoints support both schemes.
    if http_proxy and not https_proxy:
        https_proxy = http_proxy
    if https_proxy and not http_proxy:
        http_proxy = https_proxy

    proxies: Dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy

    if proxies:
        session.proxies.update(proxies)


# Model configurations
MODELS: Dict[str, Dict[str, Any]] = {
    "z-image": {
        "endpoint": "/jobs/z-image",
        "kind": "image",
        "supports_simple_generate": True,
        "name": "Z-Image",
        "description": "Simple, fast image generation",
    },
    "soul": {
        "endpoint": "/jobs/text2image-soul",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Soul Standard",
        "description": "Stylized generation (requires style_id)",
    },
    "flux-2": {
        "endpoint": "/jobs/flux-2",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Flux 2",
        "description": "Advanced model (requires input_images)",
    },
    "gpt": {
        "endpoint": "/jobs/text2image-gpt",
        "kind": "image",
        "supports_simple_generate": True,
        "name": "GPT Image",
        "description": "OpenAI-based generation",
    },
    "nano-banana-2": {
        "endpoint": "/jobs/nano-banana-2",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Nano Banana 2",
        "description": "Nano Banana variant (requires input_images)",
    },
    "nano-banana-2-static": {
        "endpoint": "/jobs/nano-banana-2-static",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Nano Banana 2 (Static)",
        "description": "Static variant (requires input_images)",
    },
    "seedream": {
        "endpoint": "/jobs/seedream",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Seedream",
        "description": "Seedream model (requires input_images)",
    },
    "seedream-v4-5": {
        "endpoint": "/jobs/seedream-v4-5",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "Seedream v4.5",
        "description": "Seedream v4.5 (requires input_images + quality)",
    },
    "openai-hazel": {
        "endpoint": "/jobs/openai-hazel",
        "kind": "image",
        "supports_simple_generate": False,
        "name": "OpenAI Hazel",
        "description": "OpenAI Hazel (not tested)",
    },
    "image2video": {
        "endpoint": "/jobs/image2video",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "Image2Video",
        "description": "Convert image to video (requires input image/config)",
    },
    "kling": {
        "endpoint": "/jobs/kling",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "Kling",
        "description": "Kling video model (requires input config)",
    },
    "veo3": {
        "endpoint": "/jobs/veo3",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "Veo3",
        "description": "Veo3 video model (requires input config)",
    },
    "wan2-5-video": {
        "endpoint": "/jobs/wan2-5-video",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "Wan 2.5 Video",
        "description": "Wan 2.5 video model (requires input config)",
    },
    "minimax-hailuo": {
        "endpoint": "/jobs/minimax-hailuo",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "MiniMax Hailuo",
        "description": "MiniMax Hailuo video model (requires input config)",
    },
    "sora2-video": {
        "endpoint": "/jobs/sora2-video",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "Sora 2 Video",
        "description": "Sora 2 video model (requires input config)",
    },
    "seedance": {
        "endpoint": "/jobs/seedance",
        "kind": "video",
        "supports_simple_generate": False,
        "name": "SeeDance",
        "description": "SeeDance video model (requires input config)",
    },
}


class HiggsFieldClient:
    """Client for Higgsfield API with Cloudflare bypass"""
    
    def __init__(self):
        self.session = requests.Session(impersonate=IMPERSONATE)
        _configure_session_proxies(self.session)
        self.jwt: Optional[str] = None
        self.session_id: Optional[str] = None
        self.user_id: Optional[str] = None
        self.email: Optional[str] = None
        self._load_session()
        
    def _load_session(self):
        """Load saved session from disk"""
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    self.jwt = data.get('jwt')
                    self.session_id = data.get('sessionId')
                    self.user_id = data.get('userId')
                    self.email = data.get('email')
                    
                    # Restore cookies
                    if 'allCookies' in data:
                        for cookie_data in data['allCookies']:
                            self.session.cookies.set(
                                cookie_data['name'],
                                cookie_data['value'],
                                domain=cookie_data['domain']
                            )
                    
                    # Also set the __client cookie specifically
                    if 'clientCookie' in data:
                        self.session.cookies.set(
                            '__client',
                            data['clientCookie'],
                            domain='.clerk.higgsfield.ai'
                        )
                        
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load session: {e}[/yellow]")
    
    def _save_session(self, session_data: Dict[str, Any]):
        """Save session to disk"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, 'w') as f:
            json.dump(session_data, f, indent=2)
        os.chmod(SESSION_FILE, 0o600)  # Secure permissions
        
    def _warmup_cloudflare(self):
        """Warm up Cloudflare session by hitting the main site"""
        try:
            self.session.get(WARMUP_URL, timeout=10)
        except Exception as e:
            console.print(f"[yellow]Warning: CF warmup failed: {e}[/yellow]")

    def _clerk_post(self, path: str, data: Optional[Dict[str, Any]] = None):
        """Send a request using Clerk's current form-encoded frontend protocol."""
        return self.session.post(
            f"{CLERK_BASE}{path}",
            data=data or {},
            params=CLERK_QUERY,
            timeout=10,
        )
    
    def _refresh_jwt(self) -> bool:
        """Refresh JWT token from Clerk"""
        if not self.session_id:
            return False
            
        try:
            resp = self._clerk_post(
                f"/v1/client/sessions/{self.session_id}/tokens"
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.jwt = data.get('jwt')
                return True
            else:
                console.print(f"[red]Failed to refresh token: {resp.status_code}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Token refresh error: {e}[/red]")
            return False
    
    def login(self, email: str, password: str) -> bool:
        """Login via Clerk email+password with device verification"""
        self._warmup_cloudflare()
        
        # Step 1: Create sign-in attempt
        console.print("🔐 Starting login...")
        try:
            resp = self._clerk_post(
                "/v1/client/sign_ins",
                {"identifier": email},
            )
            
            if resp.status_code != 200:
                console.print(f"[red]Login failed: {resp.text}[/red]")
                return False
                
            sign_in_data = resp.json()
            sign_in_id = sign_in_data['response']['id']
            
            # Check if device verification is needed
            if sign_in_data['response']['status'] == 'needs_first_factor':
                payload = {
                    "strategy": "password",
                    "password": password
                }
                resp = self._clerk_post(
                    f"/v1/client/sign_ins/{sign_in_id}/attempt_first_factor",
                    payload,
                )
                
                if resp.status_code != 200:
                    console.print(f"[red]Authentication failed: {resp.text}[/red]")
                    return False
                    
                attempt_data = resp.json()
            else:
                attempt_data = sign_in_data
            
            # Check if we need email verification code
            if attempt_data['response']['status'] == 'needs_second_factor':
                # Prepare email code verification
                payload = {
                    "strategy": "email_code",
                    "email_address_id": attempt_data['response']['supported_second_factors'][0]['email_address_id']
                }
                resp = self._clerk_post(
                    f"/v1/client/sign_ins/{sign_in_id}/prepare_second_factor",
                    payload,
                )
                
                if resp.status_code != 200:
                    console.print(f"[red]Failed to request verification code: {resp.text}[/red]")
                    return False
                
                console.print(f"📧 Verification code sent to {email}")
                code = click.prompt("Enter the 6-digit code from your email", type=str)
                
                # Verify the code
                payload = {
                    "strategy": "email_code",
                    "code": code
                }
                resp = self._clerk_post(
                    f"/v1/client/sign_ins/{sign_in_id}/attempt_second_factor",
                    payload,
                )
                
                if resp.status_code != 200:
                    console.print(f"[red]Verification failed: {resp.text}[/red]")
                    return False
                    
                attempt_data = resp.json()
            
            # Extract session info
            if attempt_data['response']['status'] == 'complete':
                client_data = attempt_data['client']
                session = client_data['sessions'][0]
                
                self.session_id = session['id']
                self.user_id = session['user']['id']
                self.email = email
                
                # Get JWT token
                if not self._refresh_jwt():
                    return False
                
                # Save session
                session_data = {
                    'sessionId': self.session_id,
                    'userId': self.user_id,
                    'email': self.email,
                    'jwt': self.jwt,
                    'savedAt': time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                    'allCookies': []
                }
                
                # Save all cookies
                for cookie in self.session.cookies.jar:
                    session_data['allCookies'].append({
                        'name': cookie.name,
                        'value': cookie.value,
                        'domain': cookie.domain
                    })
                
                # Get __client cookie specifically
                client_cookie = self.session.cookies.get('__client', domain='.clerk.higgsfield.ai')
                if client_cookie:
                    session_data['clientCookie'] = client_cookie
                
                self._save_session(session_data)
                console.print("[green]✓ Login successful![/green]")
                return True
            else:
                console.print(f"[red]Login incomplete: {attempt_data['response']['status']}[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Login error: {e}[/red]")
            import traceback
            traceback.print_exc()
            return False
    
    def _ensure_auth(self) -> bool:
        """Ensure we have a valid JWT token"""
        if not self.session_id:
            console.print("[red]Not logged in. Run 'hf login' first.[/red]")
            return False
        
        # Refresh JWT (they expire in ~60s)
        return self._refresh_jwt()

    def _post_job(self, endpoint: str, payload: Dict[str, Any], verbose: bool = False) -> Optional[str]:
        """Submit a generation job. Returns job_set_id on success."""
        url = f"{API_BASE}{endpoint}"
        headers = {"Authorization": f"Bearer {self.jwt}"}
        resp = self.session.post(url, json=payload, headers=headers, timeout=30)

        if resp.status_code != 200:
            console.print(f"[red]Generation failed: {resp.status_code} - {resp.text}[/red]")
            if verbose:
                console.print(f"[yellow]Endpoint:[/yellow] {endpoint}")
                console.print(f"[yellow]Payload:[/yellow] {json.dumps(payload, indent=2)[:2000]}")
            return None

        job_data = resp.json()

        # API sometimes returns {"id": project_id, "job_sets": [actual_job_set]}
        if isinstance(job_data, dict) and "job_sets" in job_data and job_data.get("job_sets"):
            first = job_data["job_sets"][0]
            if isinstance(first, dict) and "id" in first:
                return first["id"]

        if isinstance(job_data, dict) and "id" in job_data:
            return job_data["id"]

        if verbose:
            console.print(f"[yellow]Unexpected job response:[/yellow] {json.dumps(job_data, indent=2)[:2000]}")
        console.print("[red]Unexpected job response: missing job_set_id[/red]")
        return None

    def _wait_for_job_set(
        self,
        job_set_id: str,
        timeout_s: int,
        poll_interval_s: float = 2.0,
    ) -> Optional[Dict[str, Any]]:
        """Poll job set until completion or timeout. Returns job-set JSON on completion."""
        start = time.monotonic()
        poll_count = 0

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout_s:
                console.print("[yellow]⚠ Timeout waiting for generation[/yellow]")
                return None

            time.sleep(poll_interval_s)
            poll_count += 1

            # Refresh token periodically to prevent expiry during long jobs.
            if poll_count % 20 == 0:
                self._refresh_jwt()

            status_url = f"{API_BASE}/job-sets/{job_set_id}"
            headers = {"Authorization": f"Bearer {self.jwt}"}
            status_resp = self.session.get(status_url, headers=headers, timeout=10)
            if status_resp.status_code != 200:
                continue

            status_data = status_resp.json()
            jobs = status_data.get("jobs") or []
            statuses = [j.get("status") for j in jobs if isinstance(j, dict)]

            if statuses and all(s == "completed" for s in statuses):
                return status_data
            if any(s == "failed" for s in statuses):
                return status_data

    @staticmethod
    def _collect_urls(value: Any) -> List[str]:
        urls: List[str] = []
        if isinstance(value, dict):
            for v in value.values():
                urls.extend(HiggsFieldClient._collect_urls(v))
        elif isinstance(value, list):
            for v in value:
                urls.extend(HiggsFieldClient._collect_urls(v))
        elif isinstance(value, str):
            if value.startswith("https://") or value.startswith("http://"):
                urls.append(value)
        return urls

    @staticmethod
    def _extract_result_urls(job: Dict[str, Any]) -> List[str]:
        results = job.get("results") or {}
        ordered: List[str] = []

        def _add(u: Any) -> None:
            if isinstance(u, str) and (u.startswith("http://") or u.startswith("https://")):
                ordered.append(u)
            elif isinstance(u, list):
                for x in u:
                    _add(x)

        # Try common/expected fields first.
        _add(((results.get("raw") or {}).get("url")))
        _add(((results.get("raw") or {}).get("urls")))
        _add(((results.get("video") or {}).get("url")))
        _add(results.get("url"))

        # Fallback: scrape any URLs from the results object.
        ordered.extend(HiggsFieldClient._collect_urls(results))

        # Dedupe while preserving order.
        seen = set()
        out: List[str] = []
        for u in ordered:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    @staticmethod
    def _guess_ext_from_url(url: str, fallback_ext: str) -> str:
        try:
            path = urlparse(url).path
            ext = Path(path).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov"}:
                return ext
        except Exception:
            pass
        return fallback_ext if fallback_ext.startswith(".") else f".{fallback_ext}"

    @staticmethod
    def _build_output_path(output: Optional[str], ext: str) -> Path:
        if output:
            p = Path(output).expanduser()
            if p.exists() and p.is_dir():
                return p / f"hf_{int(time.time())}{ext}"
            if p.suffix == "":
                return p.with_suffix(ext)
            return p
        return Path.cwd() / f"hf_{int(time.time())}{ext}"

    def _download_url(self, url: str, output: Optional[str], fallback_ext: str) -> Optional[str]:
        ext = self._guess_ext_from_url(url, fallback_ext=fallback_ext)
        output_path = self._build_output_path(output, ext=ext)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            resp = self.session.get(url, timeout=60, stream=True)
        except TypeError:
            # Some curl_cffi versions may not support stream=.
            resp = self.session.get(url, timeout=60)
        if resp.status_code != 200:
            console.print(f"[red]Failed to download result: {resp.status_code}[/red]")
            return None

        try:
            # Prefer streaming if available (videos can be large).
            if hasattr(resp, "iter_content"):
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            else:
                output_path.write_bytes(resp.content)
        except Exception as e:
            console.print(f"[red]Failed to write file: {e}[/red]")
            return None

        console.print(f"[green]✓ Saved to: {output_path}[/green]")
        return str(output_path)

    def submit_job(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        output: Optional[str] = None,
        timeout_s: int = 900,
        poll_interval_s: float = 2.0,
        download: bool = True,
        fallback_ext: str = ".bin",
        verbose: bool = False,
    ) -> Optional[str]:
        """Submit a job to an arbitrary endpoint and optionally download the result."""
        if not self._ensure_auth():
            return None
        self._warmup_cloudflare()

        job_set_id = self._post_job(endpoint=endpoint, payload=payload, verbose=verbose)
        if not job_set_id:
            return None

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Waiting for completion...", total=None)
            status_data = self._wait_for_job_set(
                job_set_id=job_set_id,
                timeout_s=timeout_s,
                poll_interval_s=poll_interval_s,
            )

            if not status_data:
                return None

            jobs = status_data.get("jobs") or []
            first_job = jobs[0] if jobs else {}
            job_status = first_job.get("status")

            if job_status == "completed":
                progress.update(task, description="[green]✓ Generation complete![/green]")
            elif job_status == "failed":
                progress.update(task, description="[red]✗ Generation failed[/red]")
                if verbose:
                    console.print(json.dumps(status_data, indent=2)[:4000])
                return None

        if not isinstance(first_job, dict):
            console.print("[red]Unexpected job-set response: missing job data[/red]")
            if verbose:
                console.print(json.dumps(status_data, indent=2)[:4000])
            return None

        urls = self._extract_result_urls(first_job)
        if not urls:
            console.print("[red]No result URL found in job response[/red]")
            if verbose:
                console.print(json.dumps(status_data, indent=2)[:4000])
            return None

        result_url = urls[0]
        if not download:
            console.print(result_url)
            return result_url

        return self._download_url(result_url, output=output, fallback_ext=fallback_ext)
    
    def generate(self, prompt: str, model: str = "z-image", width: int = 1024, 
                 height: int = 1024, aspect_ratio: str = "1:1", 
                 seed: Optional[int] = None, output: Optional[str] = None) -> Optional[str]:
        """Generate an image and download it"""
        if not self._ensure_auth():
            return None

        self._warmup_cloudflare()

        model_config = MODELS.get(model)
        if not model_config:
            console.print(f"[red]Unknown model: {model}[/red]")
            return None
        if model_config.get("kind") != "image":
            console.print("[red]This command only supports image models. Use 'hf submit' for video models.[/red]")
            return None
        if not model_config.get("supports_simple_generate", False):
            console.print("[red]Model requires additional parameters not exposed by `hf generate`. Use `hf submit` with a captured payload.[/red]")
            return None
        
        # Build generation payload
        payload = {
            "params": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "batch_size": 1,
                "enhance_prompt": True
            }
        }
        
        if seed is not None:
            payload["params"]["seed"] = seed
        
        console.print(f"🎨 Generating: [cyan]{prompt}[/cyan]")

        try:
            return self.submit_job(
                endpoint=model_config["endpoint"],
                payload=payload,
                output=output,
                timeout_s=240,
                poll_interval_s=2.0,
                download=True,
                fallback_ext=".png",
                verbose=False,
            )
        except Exception as e:
            console.print(f"[red]Generation error: {e}[/red]")
            import traceback
            traceback.print_exc()
            return None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account info and credits balance"""
        if not self._ensure_auth():
            return None
        
        self._warmup_cloudflare()
        
        try:
            url = f"{API_BASE}/users/me"
            headers = {"Authorization": f"Bearer {self.jwt}"}
            resp = self.session.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                return resp.json()
            else:
                console.print(f"[red]Failed to get account info: {resp.status_code}[/red]")
                return None
        except Exception as e:
            console.print(f"[red]Error getting account info: {e}[/red]")
            return None
    
    def get_history(self, limit: int = 10) -> Optional[Dict[str, Any]]:
        """Get recent generations"""
        if not self._ensure_auth():
            return None
        
        self._warmup_cloudflare()
        
        try:
            url = f"{API_BASE}/jobs"
            headers = {"Authorization": f"Bearer {self.jwt}"}
            resp = self.session.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                # Return only the requested number of jobs
                if 'jobs' in data:
                    data['jobs'] = data['jobs'][:limit]
                return data
            else:
                console.print(f"[red]Failed to get history: {resp.status_code}[/red]")
                return None
        except Exception as e:
            console.print(f"[red]Error getting history: {e}[/red]")
            return None


# CLI Commands
@click.group()
def cli():
    """Higgsfield CLI - Generate images (and videos) via Higgsfield.ai"""
    pass


@cli.command()
@click.option('--email', prompt='Email', help='Your Higgsfield account email')
@click.option('--password', prompt='Password', hide_input=True, help='Your password')
def login(email: str, password: str):
    """Login to Higgsfield"""
    client = HiggsFieldClient()
    if client.login(email, password):
        console.print("[green]✓ Logged in successfully[/green]")
        sys.exit(0)
    else:
        console.print("[red]✗ Login failed[/red]")
        sys.exit(1)


@cli.command()
@click.argument('prompt')
@click.option('--model', '-m', default='z-image', help='Simple image model ID to use (e.g. z-image, gpt). See `hf models`.')
@click.option('--width', '-w', default=1024, help='Image width')
@click.option('--height', '-h', default=1024, help='Image height')
@click.option('--aspect-ratio', '-a', default='1:1', help='Aspect ratio (1:1, 16:9, 9:16, etc)')
@click.option('--seed', '-s', type=int, help='Random seed for reproducibility')
@click.option('--output', '-o', help='Output file path')
def generate(prompt: str, model: str, width: int, height: int, aspect_ratio: str, seed: Optional[int], output: Optional[str]):
    """Generate an image from a prompt"""
    client = HiggsFieldClient()
    result = client.generate(prompt, model=model, width=width, height=height, 
                            aspect_ratio=aspect_ratio, seed=seed, output=output)
    
    if result:
        sys.exit(0)
    else:
        sys.exit(1)


# Alias for generate
@cli.command()
@click.argument('prompt')
@click.option('--model', '-m', default='z-image', help='Simple image model ID to use (e.g. z-image, gpt). See `hf models`.')
@click.option('--width', '-w', default=1024, help='Image width')
@click.option('--height', '-h', default=1024, help='Image height')
@click.option('--aspect-ratio', '-a', default='1:1', help='Aspect ratio')
@click.option('--seed', '-s', type=int, help='Random seed')
@click.option('--output', '-o', help='Output file path')
def gen(prompt: str, model: str, width: int, height: int, aspect_ratio: str, seed: Optional[int], output: Optional[str]):
    """Alias for generate command"""
    client = HiggsFieldClient()
    result = client.generate(prompt, model=model, width=width, height=height, 
                            aspect_ratio=aspect_ratio, seed=seed, output=output)
    
    if result:
        sys.exit(0)
    else:
        sys.exit(1)


@cli.command()
@click.option('--model', '-m', help='Model ID to use (see `hf models`)')
@click.option('--endpoint', help='Raw endpoint path (e.g. /jobs/kling). Overrides --model.')
@click.option('--json-file', type=click.Path(exists=True, dir_okay=False), help='JSON file containing params or full payload')
@click.option('--json', 'json_str', help='Inline JSON string containing params or full payload')
@click.option('--raw', is_flag=True, help='Treat JSON as full payload (do not wrap in {\"params\": ...})')
@click.option('--output', '-o', help='Output file path (file or directory)')
@click.option('--timeout', default=900, show_default=True, help='Max time to wait (seconds)')
@click.option('--poll-interval', default=2.0, show_default=True, help='Polling interval (seconds)')
@click.option('--no-download', is_flag=True, help='Do not download; print the result URL and exit')
@click.option('--verbose', is_flag=True, help='Verbose output (includes payload/response snippets on errors)')
def submit(
    model: Optional[str],
    endpoint: Optional[str],
    json_file: Optional[str],
    json_str: Optional[str],
    raw: bool,
    output: Optional[str],
    timeout: int,
    poll_interval: float,
    no_download: bool,
    verbose: bool,
):
    """
    Submit a job to any Higgsfield generation endpoint (including video models).

    Pass either the full request JSON body (as seen in DevTools) or just the params object.
    By default, if the JSON does not contain a top-level "params" key, it will be wrapped
    as {"params": <your_json>}. Use --raw to disable wrapping.
    """

    if not endpoint and not model:
        raise click.ClickException("Provide --model or --endpoint")
    if endpoint and not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"

    model_cfg = MODELS.get(model) if model else None
    if not endpoint:
        if not model_cfg:
            raise click.ClickException(f"Unknown model: {model}. Run `hf models` to list available IDs.")
        endpoint = model_cfg["endpoint"]

    if (json_file is None) == (json_str is None):
        raise click.ClickException("Provide exactly one of --json-file or --json")

    try:
        if json_file is not None:
            with open(json_file, "r") as f:
                data = json.load(f)
        else:
            data = json.loads(json_str or "")
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON: {e}") from e
    except OSError as e:
        raise click.ClickException(f"Could not read file: {e}") from e

    if not isinstance(data, dict):
        raise click.ClickException("JSON must decode to an object (dictionary)")

    if raw:
        payload = data
    else:
        payload = data if "params" in data else {"params": data}

    # Guess fallback extension based on known model kind.
    fallback_ext = ".bin"
    if model_cfg and model_cfg.get("kind") == "image":
        fallback_ext = ".png"
    elif model_cfg and model_cfg.get("kind") == "video":
        fallback_ext = ".mp4"
    elif endpoint and ("video" in endpoint or endpoint.endswith("kling") or endpoint.endswith("veo3")):
        fallback_ext = ".mp4"

    client = HiggsFieldClient()
    result = client.submit_job(
        endpoint=endpoint,
        payload=payload,
        output=output,
        timeout_s=timeout,
        poll_interval_s=poll_interval,
        download=not no_download,
        fallback_ext=fallback_ext,
        verbose=verbose,
    )

    sys.exit(0 if result else 1)


@cli.command()
def models():
    """List available models"""
    table = Table(title="Available Models")
    table.add_column("ID", style="cyan")
    table.add_column("Kind", style="magenta")
    table.add_column("Name", style="green")
    table.add_column("Description", style="white")
    table.add_column("Endpoint", style="yellow")
    
    for model_id, config in MODELS.items():
        table.add_row(
            model_id,
            config.get("kind", "unknown"),
            config.get("name", ""),
            config.get("description", ""),
            config.get("endpoint", ""),
        )
    
    console.print(table)


@cli.command()
def status():
    """Show account status"""
    client = HiggsFieldClient()
    
    if not client.email:
        console.print("[red]Not logged in. Run 'hf login' first.[/red]")
        sys.exit(1)
    
    table = Table(title="Account Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Email", client.email)
    table.add_row("User ID", client.user_id)
    table.add_row("Session ID", client.session_id)
    table.add_row("Session File", str(SESSION_FILE))
    
    # Try to get additional info from API (optional)
    info = client.get_account_info()
    if info:
        if 'credits' in info:
            table.add_row("Credits", str(info['credits']))
        if 'subscription' in info:
            table.add_row("Plan", info['subscription'].get('plan', 'Free'))
    
    console.print(table)
    sys.exit(0)


@cli.command()
@click.option('--limit', '-n', default=10, help='Number of items to show')
def history(limit: int):
    """Show recent generations"""
    client = HiggsFieldClient()
    data = client.get_history(limit=limit)
    
    if data and 'jobs' in data:
        jobs = data['jobs']
        
        if not jobs:
            console.print("[yellow]No generation history found[/yellow]")
            sys.exit(0)
        
        table = Table(title=f"Recent Generations (last {len(jobs)})")
        table.add_column("Created", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Prompt", style="white", max_width=50)
        table.add_column("Status", style="yellow")
        
        for job in jobs:
            created = time.strftime('%Y-%m-%d %H:%M', time.localtime(job['created_at']))
            model_type = job.get('job_set_type', 'unknown')
            prompt = job.get('params', {}).get('prompt', 'N/A')
            status = job.get('status', 'unknown')
            
            table.add_row(created, model_type, prompt, status)
        
        console.print(table)
        sys.exit(0)
    else:
        console.print("[red]Failed to get history[/red]")
        sys.exit(1)


if __name__ == '__main__':
    cli()
