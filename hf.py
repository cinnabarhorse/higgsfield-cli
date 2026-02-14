#!/usr/bin/env python3
"""
Higgsfield CLI - Generate images via Higgsfield.ai API
"""
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any

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

# Model configurations
MODELS = {
    "z-image": {
        "endpoint": "/jobs/z-image",
        "name": "Z-Image",
        "description": "Simple, fast image generation"
    },
    "soul": {
        "endpoint": "/jobs/text2image-soul",
        "name": "Soul Standard",
        "description": "Stylized generation (requires style_id)"
    },
    "flux-2": {
        "endpoint": "/jobs/flux-2",
        "name": "Flux 2",
        "description": "Advanced model (requires input_images)"
    },
    "gpt": {
        "endpoint": "/jobs/text2image-gpt",
        "name": "GPT Image",
        "description": "OpenAI-based generation"
    }
}


class HiggsFieldClient:
    """Client for Higgsfield API with Cloudflare bypass"""
    
    def __init__(self):
        self.session = requests.Session(impersonate=IMPERSONATE)
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
                            kwargs = {}
                            if cookie_data.get('domain'):
                                kwargs['domain'] = cookie_data['domain']
                            if cookie_data.get('path'):
                                kwargs['path'] = cookie_data['path']
                            self.session.cookies.set(cookie_data['name'], cookie_data['value'], **kwargs)
                    
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

    def _clerk_init_client(self):
        """Initialize Clerk client state/cookies.

        Clerk's frontend API may return `signed_out` for some endpoints unless the
        client is initialized first.
        """
        try:
            self.session.get(f"{CLERK_BASE}/v1/client", timeout=10)
        except Exception as e:
            console.print(f"[yellow]Warning: Clerk init failed: {e}[/yellow]")
    
    def _refresh_jwt(self) -> bool:
        """Refresh JWT token from Clerk"""
        if not self.session_id:
            return False
            
        try:
            url = f"{CLERK_BASE}/v1/client/sessions/{self.session_id}/tokens"
            resp = self.session.post(url, timeout=10)
            
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
        self._clerk_init_client()
        
        # Clerk flow: identify first, then attempt factor(s).
        console.print("🔐 Starting login...")
        try:
            # Step 1: Identify (email)
            url = f"{CLERK_BASE}/v1/client/sign_ins"
            resp = self.session.post(url, data={"identifier": email}, timeout=10)
            
            if resp.status_code != 200:
                console.print(f"[red]Login failed: {resp.text}[/red]")
                return False
                
            attempt_data = resp.json()
            sign_in_id = attempt_data['response']['id']
            
            # Step 2: Password first factor
            if attempt_data['response']['status'] == 'needs_first_factor':
                supported = [
                    f.get('strategy')
                    for f in (attempt_data['response'].get('supported_first_factors') or [])
                    if isinstance(f, dict)
                ]
                if 'password' not in supported:
                    console.print(
                        f"[red]Password login not available. Supported first factors: {supported}[/red]"
                    )
                    return False

                url = f"{CLERK_BASE}/v1/client/sign_ins/{sign_in_id}/attempt_first_factor"
                resp = self.session.post(
                    url,
                    data={"strategy": "password", "password": password},
                    timeout=10,
                )
                
                if resp.status_code != 200:
                    console.print(f"[red]Authentication failed: {resp.text}[/red]")
                    return False
                    
                attempt_data = resp.json()
                sign_in_id = attempt_data['response']['id']
            
            # Check if we need email verification code
            if attempt_data['response']['status'] == 'needs_second_factor':
                # Prepare email code verification
                url = f"{CLERK_BASE}/v1/client/sign_ins/{sign_in_id}/prepare_second_factor"
                payload = {"strategy": "email_code"}

                # Some configurations include an email_address_id for second factor.
                email_address_id = None
                for factor in (attempt_data['response'].get('supported_second_factors') or []):
                    if isinstance(factor, dict) and factor.get('strategy') == 'email_code':
                        email_address_id = factor.get('email_address_id')
                        break
                if not email_address_id:
                    # Fallback: some Clerk responses only include email metadata in supported_first_factors.
                    for factor in (attempt_data['response'].get('supported_first_factors') or []):
                        if isinstance(factor, dict) and factor.get('strategy') == 'email_code':
                            email_address_id = factor.get('email_address_id')
                            break
                if email_address_id:
                    payload["email_address_id"] = email_address_id

                resp = self.session.post(url, data=payload, timeout=10)
                
                if resp.status_code != 200:
                    console.print(f"[red]Failed to request verification code: {resp.text}[/red]")
                    return False
                
                console.print(f"📧 Verification code sent to {email}")
                code = click.prompt("Enter the 6-digit code from your email", type=str)
                
                # Verify the code
                url = f"{CLERK_BASE}/v1/client/sign_ins/{sign_in_id}/attempt_second_factor"
                payload = {
                    "strategy": "email_code",
                    "code": code
                }
                resp = self.session.post(url, data=payload, timeout=10)
                
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
                cookie_jar = getattr(self.session.cookies, "jar", None) or self.session.cookies
                for cookie in cookie_jar:
                    if not hasattr(cookie, "name"):
                        continue
                    session_data['allCookies'].append({
                        'name': cookie.name,
                        'value': cookie.value,
                        'domain': getattr(cookie, 'domain', None),
                        'path': getattr(cookie, 'path', None),
                    })
                
                # Get __client cookie specifically
                client_cookie = (
                    self.session.cookies.get('__client', domain='.clerk.higgsfield.ai')
                    or self.session.cookies.get('__client')
                )
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
        
        # Submit generation job
        console.print(f"🎨 Generating: [cyan]{prompt}[/cyan]")
        
        try:
            url = f"{API_BASE}{model_config['endpoint']}"
            headers = {"Authorization": f"Bearer {self.jwt}"}
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if resp.status_code != 200:
                console.print(f"[red]Generation failed: {resp.status_code} - {resp.text}[/red]")
                return None
            
            job_data = resp.json()
            # API returns {"id": project_id, "job_sets": [actual_job_set]}
            if 'job_sets' in job_data and len(job_data['job_sets']) > 0:
                job_set_id = job_data['job_sets'][0]['id']
            else:
                # Fallback for direct job set response
                job_set_id = job_data['id']
            
            # Poll for completion
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Generating image...", total=None)
                
                max_polls = 120  # 2 minutes max
                poll_count = 0
                
                while poll_count < max_polls:
                    time.sleep(2)
                    poll_count += 1
                    
                    # Refresh token periodically
                    if poll_count % 20 == 0:
                        self._refresh_jwt()
                    
                    status_url = f"{API_BASE}/job-sets/{job_set_id}"
                    headers = {"Authorization": f"Bearer {self.jwt}"}
                    status_resp = self.session.get(status_url, headers=headers, timeout=10)
                    
                    if status_resp.status_code != 200:
                        continue
                    
                    status_data = status_resp.json()
                    job_status = status_data['jobs'][0]['status']
                    
                    if job_status == 'completed':
                        progress.update(task, description="[green]✓ Generation complete![/green]")
                        
                        # Download result
                        result_url = status_data['jobs'][0]['results']['raw']['url']
                        
                        # Determine output filename
                        if output:
                            output_path = Path(output)
                        else:
                            filename = f"hf_{int(time.time())}.png"
                            output_path = Path.cwd() / filename
                        
                        # Download image
                        img_resp = self.session.get(result_url, timeout=30)
                        if img_resp.status_code == 200:
                            output_path.write_bytes(img_resp.content)
                            console.print(f"[green]✓ Saved to: {output_path}[/green]")
                            return str(output_path)
                        else:
                            console.print(f"[red]Failed to download image: {img_resp.status_code}[/red]")
                            return None
                    
                    elif job_status == 'failed':
                        progress.update(task, description="[red]✗ Generation failed[/red]")
                        return None
                    
                    else:
                        progress.update(task, description=f"Status: {job_status}...")
                
                console.print("[yellow]⚠ Timeout waiting for generation[/yellow]")
                return None
                
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
    """Higgsfield CLI - Generate images via Higgsfield.ai"""
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
@click.option('--model', '-m', default='z-image', help='Model to use (z-image, soul, flux-2, gpt)')
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
@click.option('--model', '-m', default='z-image', help='Model to use')
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
def models():
    """List available models"""
    table = Table(title="Available Models")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description", style="white")
    
    for model_id, config in MODELS.items():
        table.add_row(model_id, config['name'], config['description'])
    
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
