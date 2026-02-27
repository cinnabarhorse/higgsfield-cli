#!/usr/bin/env python3
"""
Higgsfield CLI - Generate images and videos via Higgsfield.ai API
"""
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
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

VIDEO_MODELS = {
    "kling3_0": {
        "endpoint": "/jobs/v2/kling3_0",
        "name": "Kling 3.0",
        "description": "Text-to-video generation"
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
        
        # Step 1: Create sign-in attempt
        console.print("🔐 Starting login...")
        try:
            url = f"{CLERK_BASE}/v1/client/sign_ins"
            payload = {
                "identifier": email,
                "strategy": "password",
                "password": password
            }
            resp = self.session.post(url, json=payload, timeout=10)
            
            if resp.status_code != 200:
                console.print(f"[red]Login failed: {resp.text}[/red]")
                return False
                
            sign_in_data = resp.json()
            sign_in_id = sign_in_data['response']['id']
            
            # Check if device verification is needed
            if sign_in_data['response']['status'] == 'needs_first_factor':
                # Already verified, get session
                url = f"{CLERK_BASE}/v1/client/sign_ins/{sign_in_id}/attempt_first_factor"
                payload = {
                    "strategy": "password",
                    "password": password
                }
                resp = self.session.post(url, json=payload, timeout=10)
                
                if resp.status_code != 200:
                    console.print(f"[red]Authentication failed: {resp.text}[/red]")
                    return False
                    
                attempt_data = resp.json()
            else:
                attempt_data = sign_in_data
            
            # Check if we need email verification code
            if attempt_data['response']['status'] == 'needs_second_factor':
                # Prepare email code verification
                url = f"{CLERK_BASE}/v1/client/sign_ins/{sign_in_id}/prepare_second_factor"
                payload = {
                    "strategy": "email_code",
                    "email_address_id": attempt_data['response']['supported_second_factors'][0]['email_address_id']
                }
                resp = self.session.post(url, json=payload, timeout=10)
                
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
                resp = self.session.post(url, json=payload, timeout=10)
                
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
                for cookie in self.session.cookies:
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

    def _submit_job(self, endpoint: str, payload: Dict[str, Any]) -> Optional[str]:
        """Submit job and return job_set_id"""
        try:
            url = f"{API_BASE}{endpoint}"
            headers = {"Authorization": f"Bearer {self.jwt}"}
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)

            if resp.status_code != 200:
                console.print(f"[red]Generation failed: {resp.status_code} - {resp.text}[/red]")
                return None

            job_data = resp.json()
            # API often returns {"id": project_id, "job_sets": [actual_job_set]}
            if "job_sets" in job_data and len(job_data["job_sets"]) > 0:
                return job_data["job_sets"][0]["id"]
            # Fallback for direct job-set response
            return job_data["id"]
        except Exception as e:
            console.print(f"[red]Job submission error: {e}[/red]")
            return None

    def _poll_job_set(self, job_set_id: str, task_text: str, max_polls: int) -> Optional[Dict[str, Any]]:
        """Poll job set until completed/failed/timeout"""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(task_text, total=None)
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
                if "jobs" not in status_data or not status_data["jobs"]:
                    continue

                job_status = status_data["jobs"][0].get("status")
                if job_status == "completed":
                    progress.update(task, description="[green]✓ Generation complete![/green]")
                    return status_data
                if job_status == "failed":
                    progress.update(task, description="[red]✗ Generation failed[/red]")
                    return None

                progress.update(task, description=f"Status: {job_status}...")

            console.print("[yellow]⚠ Timeout waiting for generation[/yellow]")
            return None

    def _find_first_url(self, value: Any) -> Optional[str]:
        """Find first URL in nested response object."""
        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://"):
                return value
            return None
        if isinstance(value, list):
            for item in value:
                found = self._find_first_url(item)
                if found:
                    return found
            return None
        if isinstance(value, dict):
            for item in value.values():
                found = self._find_first_url(item)
                if found:
                    return found
            return None
        return None

    def _extract_result_url(self, status_data: Dict[str, Any]) -> Optional[str]:
        """Extract media URL from completed job response."""
        jobs = status_data.get("jobs") or []
        if not jobs:
            return None
        results = jobs[0].get("results") or {}
        if not isinstance(results, dict):
            return None

        raw = results.get("raw") or {}
        if isinstance(raw, dict) and isinstance(raw.get("url"), str):
            return raw["url"]
        if isinstance(results.get("url"), str):
            return results["url"]
        video = results.get("video") or {}
        if isinstance(video, dict) and isinstance(video.get("url"), str):
            return video["url"]

        return self._find_first_url(results)

    def _download_result(self, result_url: str, output: Optional[str], default_ext: str) -> Optional[str]:
        """Download generated media file."""
        if output:
            output_path = Path(output).expanduser()
            if output_path.suffix == "":
                output_path = output_path.with_suffix(default_ext)
        else:
            output_path = Path.cwd() / f"hf_{int(time.time())}{default_ext}"

        # If URL contains extension, use it unless user explicitly set output path extension.
        if not output:
            ext_from_url = Path(urlparse(result_url).path).suffix
            if ext_from_url:
                output_path = output_path.with_suffix(ext_from_url)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        media_resp = self.session.get(result_url, timeout=120)
        if media_resp.status_code != 200:
            console.print(f"[red]Failed to download media: {media_resp.status_code}[/red]")
            return None

        output_path.write_bytes(media_resp.content)
        console.print(f"[green]✓ Saved to: {output_path}[/green]")
        return str(output_path)

    def _create_media_upload(self, content_type: str, source: str = "user_upload") -> Optional[Dict[str, Any]]:
        """Create media upload target via /media/batch."""
        url = f"{API_BASE}/media/batch"
        headers = {"Authorization": f"Bearer {self.jwt}"}
        payload = {
            "mimetypes": [content_type],
            "source": source,
        }
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code != 200:
                console.print(f"[red]Failed to create media upload target: {resp.status_code} - {resp.text}[/red]")
                return None
            data = resp.json()
            if not isinstance(data, list) or not data:
                console.print("[red]Unexpected media batch response[/red]")
                return None
            media = data[0]
            if not isinstance(media, dict):
                console.print("[red]Unexpected media item response[/red]")
                return None
            return media
        except Exception as e:
            console.print(f"[red]Media batch request error: {e}[/red]")
            return None

    def _upload_media_binary(self, upload_url: str, file_path: Path, content_type: str) -> bool:
        """Upload local file bytes to pre-signed URL."""
        try:
            data = file_path.read_bytes()
            headers = {"Content-Type": content_type}
            resp = self.session.put(upload_url, data=data, headers=headers, timeout=120)
            if resp.status_code not in (200, 201, 204):
                console.print(f"[red]Media upload failed: {resp.status_code} - {resp.text}[/red]")
                return False
            return True
        except Exception as e:
            console.print(f"[red]Media upload error: {e}[/red]")
            return False

    def _finalize_media_upload(self, media_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Best-effort finalize call for uploaded media."""
        url = f"{API_BASE}/media/{media_id}/upload"
        headers = {"Authorization": f"Bearer {self.jwt}"}
        payload = {"filename": filename}
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    return data
                return None
            # Not all backend variants require/implement this finalize call.
            return None
        except Exception:
            return None

    def upload_media(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Upload a local image and return media metadata usable in generation params."""
        if not self._ensure_auth():
            return None

        self._warmup_cloudflare()

        path = Path(image_path).expanduser()
        if not path.exists() or not path.is_file():
            console.print(f"[red]Image file not found: {path}[/red]")
            return None

        guessed_content_type, _ = mimetypes.guess_type(str(path))
        content_type = guessed_content_type or "application/octet-stream"

        media = self._create_media_upload(content_type=content_type, source="user_upload")
        if not media:
            return None

        upload_url = media.get("upload_url")
        if not isinstance(upload_url, str) or not upload_url:
            console.print("[red]Missing upload_url in media response[/red]")
            return None

        console.print(f"📤 Uploading image: [cyan]{path.name}[/cyan]")
        if not self._upload_media_binary(upload_url=upload_url, file_path=path, content_type=content_type):
            return None

        media_id = media.get("id")
        if isinstance(media_id, str):
            finalized = self._finalize_media_upload(media_id=media_id, filename=path.name)
            if isinstance(finalized, dict):
                # Merge any finalized metadata over original media object.
                merged = dict(media)
                merged.update(finalized)
                media = merged

        console.print("[green]✓ Image upload complete[/green]")
        return media

    def _build_conditioning_media(self, image_path: str, role: str) -> Optional[Dict[str, Any]]:
        """Upload image and return media payload entry for kling params.medias."""
        media = self.upload_media(image_path)
        if not media:
            return None

        media_data: Dict[str, Any] = {}
        for key in ("id", "url", "content_type"):
            value = media.get(key)
            if value is not None:
                media_data[key] = value
        if not media_data:
            console.print("[red]Uploaded media response missing required data[/red]")
            return None

        return {
            "role": role,
            "data": media_data,
        }
    
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
        
        console.print(f"🎨 Generating: [cyan]{prompt}[/cyan]")
        
        job_set_id = self._submit_job(model_config["endpoint"], payload)
        if not job_set_id:
            return None

        status_data = self._poll_job_set(
            job_set_id=job_set_id,
            task_text="Generating image...",
            max_polls=120,  # 2 minutes
        )
        if not status_data:
            return None

        result_url = self._extract_result_url(status_data)
        if not result_url:
            console.print("[red]Could not find image URL in job response[/red]")
            return None

        return self._download_result(result_url, output=output, default_ext=".png")

    def generate_kling3_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        duration: int = 5,
        mode: str = "std",
        sound: str = "on",
        cfg_scale: float = 0.5,
        enhance_prompt: bool = True,
        use_free_gens: bool = False,
        use_unlim: bool = False,
        start_image: Optional[str] = None,
        end_image: Optional[str] = None,
        output: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a video with Kling 3.0 and download it."""
        if not self._ensure_auth():
            return None

        self._warmup_cloudflare()

        medias = []
        if start_image:
            start_media = self._build_conditioning_media(start_image, role="start_image")
            if not start_media:
                return None
            medias.append(start_media)
        if end_image:
            end_media = self._build_conditioning_media(end_image, role="end_image")
            if not end_media:
                return None
            medias.append(end_media)

        payload = {
            "params": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "mode": mode,
                "sound": sound,
                "duration": duration,
                "medias": medias,
                "multi_shots": False,
                "multi_prompt": [],
                "cfg_scale": cfg_scale,
                "kling_elements": [],
                "kling_element_ids": [],
                "multi_shot_mode": "auto",
                "reference_elements": [],
                "enhance_prompt": enhance_prompt,
            },
            "use_free_gens": use_free_gens,
            "use_unlim": use_unlim,
        }

        console.print(f"🎬 Generating video: [cyan]{prompt}[/cyan]")

        job_set_id = self._submit_job(VIDEO_MODELS["kling3_0"]["endpoint"], payload)
        if not job_set_id:
            return None

        status_data = self._poll_job_set(
            job_set_id=job_set_id,
            task_text="Generating video...",
            max_polls=450,  # 15 minutes
        )
        if not status_data:
            return None

        result_url = self._extract_result_url(status_data)
        if not result_url:
            console.print("[red]Could not find video URL in job response[/red]")
            return None

        return self._download_result(result_url, output=output, default_ext=".mp4")
    
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
    """Higgsfield CLI - Generate images and videos via Higgsfield.ai"""
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


@cli.command()
@click.argument('prompt')
@click.option('--model', '-m', default='kling3_0', type=click.Choice(list(VIDEO_MODELS.keys())), help='Video model to use')
@click.option('--aspect-ratio', '-a', default='16:9', help='Aspect ratio (16:9, 9:16, 1:1, etc)')
@click.option('--duration', '-d', default=5, type=int, help='Duration in seconds')
@click.option('--mode', default='std', help='Generation mode (e.g. std)')
@click.option('--sound', type=click.Choice(['on', 'off']), default='on', help='Enable or disable sound')
@click.option('--cfg-scale', default=0.5, type=float, help='CFG scale')
@click.option('--no-enhance-prompt', is_flag=True, help='Disable prompt enhancement')
@click.option('--use-free-gens', is_flag=True, help='Use free generations if available')
@click.option('--use-unlim', is_flag=True, help='Use unlimited generation pool if available')
@click.option('--start-image', type=click.Path(exists=True, dir_okay=False), help='Optional reference image path')
@click.option('--end-image', type=click.Path(exists=True, dir_okay=False), help='Optional end-frame image path')
@click.option('--output', '-o', help='Output video path')
def video(
    prompt: str,
    model: str,
    aspect_ratio: str,
    duration: int,
    mode: str,
    sound: str,
    cfg_scale: float,
    no_enhance_prompt: bool,
    use_free_gens: bool,
    use_unlim: bool,
    start_image: Optional[str],
    end_image: Optional[str],
    output: Optional[str],
):
    """Generate a video from a text prompt (currently Kling 3.0)."""
    if duration <= 0:
        console.print("[red]Duration must be greater than 0[/red]")
        sys.exit(1)

    client = HiggsFieldClient()

    if model != "kling3_0":
        console.print(f"[red]Unsupported video model: {model}[/red]")
        sys.exit(1)

    result = client.generate_kling3_video(
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        duration=duration,
        mode=mode,
        sound=sound,
        cfg_scale=cfg_scale,
        enhance_prompt=not no_enhance_prompt,
        use_free_gens=use_free_gens,
        use_unlim=use_unlim,
        start_image=start_image,
        end_image=end_image,
        output=output,
    )

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
    table.add_column("Kind", style="magenta")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description", style="white")
    
    for model_id, config in MODELS.items():
        table.add_row("image", model_id, config['name'], config['description'])
    for model_id, config in VIDEO_MODELS.items():
        table.add_row("video", model_id, config['name'], config['description'])
    
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
