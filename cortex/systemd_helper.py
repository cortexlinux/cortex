import os
import getpass
from rich.prompt import Prompt, Confirm
from cortex.branding import console, cx_header, cx_print

class SystemdHelper:
    """
    Interactive helper to generate systemd service files.
    """

    def __init__(self):
        self.service_name = ""
        self.description = ""
        self.exec_start = ""
        self.working_dir = ""
        self.user = ""
        self.restart_policy = "always"

    def run(self):
        """Interactive wizard."""
        cx_header("Systemd Service Generator")
        
        console.print("[dim]This wizard will help you create a systemd service file.[/dim]\n")

        # 1. Service Name
        self.service_name = Prompt.ask(
            "[bold cyan]Service Name[/bold cyan] (e.g. myserver)", 
            default="myservice"
        )
        if not self.service_name.endswith(".service"):
            filename = f"{self.service_name}.service"
        else:
            filename = self.service_name
            self.service_name = filename[:-8]

        # 2. Description
        self.description = Prompt.ask(
            "[bold cyan]Description[/bold cyan]", 
            default=f"Service for {self.service_name}"
        )

        # 3. ExecStart
        self.exec_start = Prompt.ask(
            "[bold cyan]Command to run (ExecStart)[/bold cyan]",
            default="/usr/bin/python3 /path/to/app.py"
        )

        # 4. Working Directory
        current_dir = os.getcwd()
        self.working_dir = Prompt.ask(
            "[bold cyan]Working Directory[/bold cyan]", 
            default=current_dir
        )

        # 5. User
        current_user = getpass.getuser()
        self.user = Prompt.ask(
            "[bold cyan]Run as User[/bold cyan]", 
            default=current_user
        )

        # 6. Restart Policy
        self.restart_policy = Prompt.ask(
            "[bold cyan]Restart Policy[/bold cyan]", 
            choices=["always", "on-failure", "no"], 
            default="always"
        )

        # Generate Content
        content = self.generate_service_content()
        
        cx_header("Generated Content")
        console.print(content, style="dim")
        console.print()

        # Save?
        if Confirm.ask(f"Save to [bold green]{filename}[/bold green] in current directory?"):
            self.save_file(filename, content)
            
            cx_print(f"File saved: {filename}", "success")
            console.print(f"\n[bold]Next Steps:[/bold]")
            console.print(f"1. Move to systemd: [cyan]sudo mv {filename} /etc/systemd/system/[/cyan]")
            console.print(f"2. Reload daemon:   [cyan]sudo systemctl daemon-reload[/cyan]")
            console.print(f"3. Enable service:  [cyan]sudo systemctl enable {self.service_name}[/cyan]")
            console.print(f"4. Start service:   [cyan]sudo systemctl start {self.service_name}[/cyan]")

    def generate_service_content(self) -> str:
        """Generates the .service file content."""
        return f"""[Unit]
Description={self.description}
After=network.target

[Service]
Type=simple
User={self.user}
WorkingDirectory={self.working_dir}
ExecStart={self.exec_start}
Restart={self.restart_policy}

[Install]
WantedBy=multi-user.target
"""

    def save_file(self, filename: str, content: str):
        """Saves content to file."""
        try:
            with open(filename, "w") as f:
                f.write(content)
        except Exception as e:
            cx_print(f"Error saving file: {e}", "error")
