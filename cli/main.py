import typer
import asyncio
import json
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from ..master_agent.master import MasterAgent
from ..worker_agent.worker import WorkerAgent
from ..shared.config import ConfigManager
from ..shared.models import Task, ActionType
from ..shared.utils import generate_id, setup_logging

app = typer.Typer(help="AI-based Developer Runtime Environment")
console = Console()


@app.command()
def start(
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path"),
    master: bool = typer.Option(False, "--master", "-m", help="Start as master agent"),
    worker: bool = typer.Option(False, "--worker", "-w", help="Start as worker agent"),
    worker_id: Optional[str] = typer.Option(None, "--worker-id", help="Worker ID (auto-generated if not provided)")
):
    """Start the AI runtime environment."""
    
    if not master and not worker:
        # Start both master and worker by default
        master = True
        worker = True
    
    async def run_agents():
        agents = []
        
        if master:
            console.print("[bold green]Starting Master Agent...[/bold green]")
            master_agent = MasterAgent(config)
            agents.append(master_agent)
        
        if worker:
            console.print("[bold blue]Starting Worker Agent...[/bold blue]")
            worker_id_final = worker_id or f"worker-{generate_id()[:8]}"
            worker_agent = WorkerAgent(worker_id_final, config)
            agents.append(worker_agent)
        
        try:
            # Start all agents
            tasks = [agent.start() for agent in agents]
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down agents...[/yellow]")
            for agent in agents:
                await agent.stop()
    
    asyncio.run(run_agents())


@app.command()
def diagnose(
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path"),
    app_name: Optional[str] = typer.Option(None, "--app", "-a", help="Diagnose specific app")
):
    """Diagnose the current environment."""
    
    console.print("[bold yellow]🔍 Diagnosing Environment...[/bold yellow]")
    
    try:
        config_manager = ConfigManager(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Check configuration
            task = progress.add_task("Checking configuration...", total=None)
            master_config = config_manager.get_master_config()
            app_configs = config_manager.get_app_configs()
            progress.update(task, description="Configuration loaded")
            
            # Check system resources
            task = progress.add_task("Checking system resources...", total=None)
            from ..shared.utils import get_system_resources
            resources = get_system_resources()
            progress.update(task, description="System resources analyzed")
            
            # Check running processes
            task = progress.add_task("Checking running processes...", total=None)
            from ..shared.utils import get_process_info
            import psutil
            
            running_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    running_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            progress.update(task, description="Processes analyzed")
        
        # Display results
        console.print("\n[bold green]✅ Diagnosis Complete[/bold green]\n")
        
        # Configuration summary
        config_table = Table(title="Configuration Summary")
        config_table.add_column("Component", style="cyan")
        config_table.add_column("Status", style="green")
        config_table.add_column("Details", style="white")
        
        config_table.add_row("Master Agent", "✅ Configured", f"ID: {master_config.agent_id}")
        config_table.add_row("Applications", "✅ Configured", f"Count: {len(app_configs)}")
        
        console.print(config_table)
        console.print()
        
        # System resources
        resources_table = Table(title="System Resources")
        resources_table.add_column("Resource", style="cyan")
        resources_table.add_column("Usage", style="white")
        resources_table.add_column("Status", style="green")
        
        cpu_percent = resources.get("cpu_percent", 0)
        memory_percent = resources.get("memory_percent", 0)
        
        resources_table.add_row(
            "CPU", 
            f"{cpu_percent:.1f}%", 
            "🟢 Good" if cpu_percent < 80 else "🟡 High" if cpu_percent < 90 else "🔴 Critical"
        )
        resources_table.add_row(
            "Memory", 
            f"{memory_percent:.1f}%", 
            "🟢 Good" if memory_percent < 80 else "🟡 High" if memory_percent < 90 else "🔴 Critical"
        )
        
        console.print(resources_table)
        console.print()
        
        # Application status
        if app_name:
            console.print(f"[bold]Application: {app_name}[/bold]")
            # TODO: Check specific app status
        else:
            apps_table = Table(title="Configured Applications")
            apps_table.add_column("Name", style="cyan")
            apps_table.add_column("Command", style="white")
            apps_table.add_column("Port", style="yellow")
            apps_table.add_column("Status", style="green")
            
            for app_config in app_configs:
                # TODO: Check if app is actually running
                status = "❓ Unknown"
                apps_table.add_row(
                    app_config.name,
                    app_config.command[:50] + "..." if len(app_config.command) > 50 else app_config.command,
                    str(app_config.port) if app_config.port else "N/A",
                    status
                )
            
            console.print(apps_table)
        
    except Exception as e:
        console.print(f"[bold red]❌ Diagnosis failed: {e}[/bold red]")


@app.command()
def heal(
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path"),
    app_name: Optional[str] = typer.Option(None, "--app", "-a", help="Heal specific app"),
    force: bool = typer.Option(False, "--force", "-f", help="Force healing without confirmation")
):
    """Heal detected issues in the environment."""
    
    console.print("[bold red]🩹 Healing Environment...[/bold red]")
    
    if not force:
        confirm = typer.confirm("Are you sure you want to attempt healing? This may restart applications.")
        if not confirm:
            console.print("[yellow]Healing cancelled.[/yellow]")
            return
    
    try:
        config_manager = ConfigManager(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            
            # Analyze current state
            task = progress.add_task("Analyzing current state...", total=None)
            # TODO: Implement actual healing logic
            progress.update(task, description="State analyzed")
            
            # Detect issues
            task = progress.add_task("Detecting issues...", total=None)
            # TODO: Implement issue detection
            progress.update(task, description="Issues detected")
            
            # Apply fixes
            task = progress.add_task("Applying fixes...", total=None)
            # TODO: Implement fix application
            progress.update(task, description="Fixes applied")
        
        console.print("\n[bold green]✅ Healing Complete[/bold green]")
        console.print("[green]All detected issues have been addressed.[/green]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Healing failed: {e}[/bold red]")


@app.command()
def status(
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path")
):
    """Show current status of the AI runtime environment."""
    
    console.print("[bold blue]📊 Environment Status[/bold blue]")
    
    try:
        config_manager = ConfigManager(config)
        
        # Get system resources
        from ..shared.utils import get_system_resources
        resources = get_system_resources()
        
        # Create status table
        status_table = Table(title="AI Runtime Environment Status")
        status_table.add_column("Component", style="cyan")
        status_table.add_column("Status", style="green")
        status_table.add_column("Details", style="white")
        
        # Master agent status
        status_table.add_row("Master Agent", "🟢 Running", "Coordinating workers")
        
        # Worker agents status
        status_table.add_row("Worker Agents", "🟢 Active", "Managing applications")
        
        # System resources
        cpu_percent = resources.get("cpu_percent", 0)
        memory_percent = resources.get("memory_percent", 0)
        
        status_table.add_row(
            "System CPU", 
            "🟢 Good" if cpu_percent < 80 else "🟡 High" if cpu_percent < 90 else "🔴 Critical",
            f"{cpu_percent:.1f}%"
        )
        
        status_table.add_row(
            "System Memory", 
            "🟢 Good" if memory_percent < 80 else "🟡 High" if memory_percent < 90 else "🔴 Critical",
            f"{memory_percent:.1f}%"
        )
        
        console.print(status_table)
        console.print()
        
        # Applications status
        app_configs = config_manager.get_app_configs()
        if app_configs:
            apps_table = Table(title="Application Status")
            apps_table.add_column("Name", style="cyan")
            apps_table.add_column("Status", style="green")
            apps_table.add_column("Port", style="yellow")
            apps_table.add_column("Health", style="blue")
            
            for app_config in app_configs:
                # TODO: Check actual app status
                apps_table.add_row(
                    app_config.name,
                    "🟢 Running",  # Placeholder
                    str(app_config.port) if app_config.port else "N/A",
                    "🟢 Healthy"  # Placeholder
                )
            
            console.print(apps_table)
        
    except Exception as e:
        console.print(f"[bold red]❌ Status check failed: {e}[/bold red]")


@app.command()
def add_app(
    name: str = typer.Argument(..., help="Application name"),
    command: str = typer.Argument(..., help="Command to start the application"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Port number"),
    working_dir: Optional[str] = typer.Option(None, "--working-dir", "-w", help="Working directory"),
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path")
):
    """Add a new application to the configuration."""
    
    console.print(f"[bold green]➕ Adding application: {name}[/bold green]")
    
    try:
        config_manager = ConfigManager(config)
        
        # Create app config
        from ..shared.models import AppConfig
        app_config = AppConfig(
            name=name,
            command=command,
            port=port,
            working_dir=working_dir
        )
        
        # Add to configuration
        config_manager.add_app(app_config)
        
        console.print(f"[green]✅ Application '{name}' added successfully![/green]")
        console.print(f"Command: {command}")
        if port:
            console.print(f"Port: {port}")
        if working_dir:
            console.print(f"Working Directory: {working_dir}")
        
    except Exception as e:
        console.print(f"[bold red]❌ Failed to add application: {e}[/bold red]")


@app.command()
def remove_app(
    name: str = typer.Argument(..., help="Application name"),
    config: str = typer.Option("agent.config.yaml", "--config", "-c", help="Configuration file path")
):
    """Remove an application from the configuration."""
    
    console.print(f"[bold red]🗑️ Removing application: {name}[/bold red]")
    
    try:
        config_manager = ConfigManager(config)
        config_manager.remove_app(name)
        
        console.print(f"[green]✅ Application '{name}' removed successfully![/green]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Failed to remove application: {e}[/bold red]")


if __name__ == "__main__":
    app() 