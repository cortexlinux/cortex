import json
import os
import subprocess

from typing import Dict, List, Optional, Tuple

from rich.prompt import Confirm, Prompt
from rich.table import Table

from cortex.branding import console, cx_header


class DockerPermissionFixer:
    """
    Diagnoses and suggests fixes for Docker container permission issues,
    specifically focusing on bind mounts and UID/GID mapping.
    """

    def __init__(self) -> None:
        """Initialize the Docker permission fixer with current host UID/GID.

        Attributes:
            host_uid: The current user's UID on the host system.
            host_gid: The current user's GID on the host system.

        Raises:
            OSError: If running on a non-POSIX system (e.g., Windows).
        """
        if not hasattr(os, 'getuid'):
            raise OSError("DockerPermissionFixer requires a POSIX-compatible system.")
        self.host_uid = os.getuid()
        self.host_gid = os.getgid()

    def _run_docker_command(self, args: List[str]) -> Tuple[bool, str, str]:
        """Run a docker command and return (success, stdout, stderr)."""
        try:
            result = subprocess.run(
                ["docker"] + args,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode == 0, result.stdout, result.stderr
        except FileNotFoundError:
            return False, "", "Docker executable not found."
        except Exception as e:
            return False, "", str(e)

    def list_containers(self) -> List[Dict[str, str]]:
        """List running containers."""
        success, stdout, stderr = self._run_docker_command(
            ["ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}"]
        )
        if not success:
            console.print(f"[red]Error listing containers: {stderr}[/red]")
            return []

        containers = []
        for line in stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) == 4:
                containers.append({
                    "id": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3]
                })
        return containers

    def inspect_container(self, container_id: str) -> Optional[Dict]:
        """Get container inspection data."""
        success, stdout, stderr = self._run_docker_command(["inspect", container_id])
        if not success:
            console.print(f"[red]Error inspecting container: {stderr}[/red]")
            return None
        try:
            data = json.loads(stdout)
            return data[0] if data else None
        except json.JSONDecodeError:
            return None

    def diagnose(self, container_id: str) -> None:
        """Diagnose permission issues for a specific container."""
        details = self.inspect_container(container_id)
        if not details:
            return

        container_name = details.get("Name", "").lstrip("/")
        config = details.get("Config", {})
        container_user = config.get("User", "")
        
        console.print(f"\n[bold cyan]Diagnosing Container: {container_name}[/bold cyan] ({container_id[:12]})")
        
        # 1. Check Container User
        effective_uid = 0 # Default to root if not specified
        effective_gid = 0
        
        if container_user:
            console.print(f"  Existing User Config: [yellow]{container_user}[/yellow]")
            # Try to parse UID:GID
            parts = container_user.split(":")
            try:
                effective_uid = int(parts[0])
                if len(parts) > 1:
                    effective_gid = int(parts[1])
            except ValueError:
                console.print(f"  [dim]User '{container_user}' is a name, assuming mapped to UID inside image.[/dim]")
                # In a real tool, we might exec into container to check 'id', but let's keep it simple/safe
        else:
            console.print("  Existing User Config: [red]Root (0:0)[/red] (Default)")

        # 2. Check Bind Mounts
        mounts = details.get("Mounts", [])
        bind_mounts = [m for m in mounts if m["Type"] == "bind"]
        
        if not bind_mounts:
            console.print("  [green]No bind mounts detected. Permission issues unlikely.[/green]")
            return

        console.print(f"  [bold]Found {len(bind_mounts)} bind mounts:[/bold]")
        
        issues_found = False
        
        for mount in bind_mounts:
            source = mount["Source"]
            destination = mount["Destination"]
            rw = mount["RW"]
            
            if not os.path.exists(source):
                console.print(f"    [dim]{source} -> {destination} (Site not found)[/dim]")
                continue

            try:
                stat = os.stat(source)
                owner_uid = stat.st_uid
                owner_gid = stat.st_gid
                
                status_icon = "✅"
                
                # Logic: If container runs as root (0), it can access host files (usually).
                # But files created by container will be root-owned on host, causing issues for host user.
                # If container runs as non-root (e.g. 1000), it needs host files to be 1000 or readable/writable by 1000.
                
                is_root_container = (effective_uid == 0)
                
                issues = []
                
                if is_root_container:
                    if rw:
                        issues.append("[yellow]Writes will be owned by root on host[/yellow]")
                        status_icon = "⚠️"
                else:
                    # Non-root container
                    if owner_uid != effective_uid:
                        # Mismatched UID. Can we write?
                        # This is a simplification. Group permissions matter too.
                        issues.append(f"[red]UID mismatch[/red] (Host: {owner_uid}, Container: {effective_uid})")
                        status_icon = "❌"
                        issues_found = True

                issue_str = f" - {', '.join(issues)}" if issues else ""
                
                console.print(f"    {status_icon} [bold]{source}[/bold]")
                console.print(f"       -> {destination}")
                console.print(f"       Host Owner: UID={owner_uid}, GID={owner_gid} {issue_str}")

            except Exception as e:
                console.print(f"    ❓ {source}: {e}")

        # 3. Recommendations
        console.print("\n[bold]Recommendations:[/bold]")
        
        if effective_uid == 0:
             console.print("\n[bold yellow]Option 1: Run as current host user[/bold yellow]")
             console.print("To avoid root-owned files on your host machine, perform user mapping:")
             console.print(f"\n  [dim]# docker run command[/dim]")
             console.print(f"  docker run [green]--user {self.host_uid}:{self.host_gid}[/green] ...")
             console.print(f"\n  [dim]# docker-compose.yml[/dim]")
             console.print(f"  services:")
             console.print(f"    {container_name}:")
             console.print(f"      [green]user: \"{self.host_uid}:{self.host_gid}\"[/green]")
        
        if issues_found:
             console.print("\n[bold red]Option 2: Fix Host Permissions[/bold red]")
             console.print("If the container *must* run as a specific user (e.g. postgres=999), change host ownership:")
             for mount in bind_mounts:
                 source = mount["Source"]
                 if os.path.exists(source):
                     # If we knew the target UID strictly, we'd use that. 
                     # For now, warn user to check container docs.
                      console.print(f"  sudo chown -R <container_uid>:<container_gid> {source}")

    def run(self) -> None:
        """Interactive wizard."""
        cx_header("Docker Permission Fixer")
        console.print(f"Host User: UID=[bold green]{self.host_uid}[/bold green], GID=[bold green]{self.host_gid}[/bold green]")
        
        containers = self.list_containers()
        if not containers:
            console.print("No running containers found.")
            return

        table = Table(title="Running Containers")
        table.add_column("#", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Image", style="blue")
        table.add_column("Status", style="green")

        options = {}
        for idx, c in enumerate(containers, 1):
            table.add_row(str(idx), c["name"], c["image"], c["status"])
            options[str(idx)] = c["id"]

        console.print(table)
        
        choice = Prompt.ask("Select a container to diagnose", choices=list(options.keys()))
        container_id = options[choice]
        
        self.diagnose(container_id)

if __name__ == "__main__":
    fixer = DockerPermissionFixer()
    fixer.run()
