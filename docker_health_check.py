"""Docker Desktop Container Health Status Checker."""

import sys

try:
    import docker
except ImportError:
    print("ERROR: 'docker' package not installed. Run: pip install docker")
    sys.exit(1)

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    print("ERROR: 'colorama' package not installed. Run: pip install colorama")
    sys.exit(1)


def get_health_status(container):
    """Extract health status from container attributes."""
    state = container.attrs.get("State", {})
    health = state.get("Health", {})
    if health:
        return health.get("Status", "no healthcheck")
    return "no healthcheck"


def colorize_status(status):
    """Return colored status string based on container state."""
    status_lower = status.lower()
    if status_lower == "running":
        return Fore.GREEN + status + Style.RESET_ALL
    elif status_lower in ("exited", "dead"):
        return Fore.RED + status + Style.RESET_ALL
    elif status_lower in ("paused", "restarting", "created"):
        return Fore.YELLOW + status + Style.RESET_ALL
    return Fore.WHITE + status + Style.RESET_ALL


def colorize_health(health):
    """Return colored health string."""
    health_lower = health.lower()
    if health_lower == "healthy":
        return Fore.GREEN + health + Style.RESET_ALL
    elif health_lower == "unhealthy":
        return Fore.RED + health + Style.RESET_ALL
    elif health_lower == "starting":
        return Fore.YELLOW + health + Style.RESET_ALL
    return Fore.CYAN + health + Style.RESET_ALL


def main():
    print(Fore.CYAN + Style.BRIGHT + "\n=== Docker Container Health Check ===" + Style.RESET_ALL)
    print()

    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as e:
        print(Fore.RED + f"ERROR: Cannot connect to Docker Desktop." + Style.RESET_ALL)
        print(Fore.RED + f"Details: {e}" + Style.RESET_ALL)
        print(Fore.YELLOW + "Make sure Docker Desktop is running." + Style.RESET_ALL)
        sys.exit(1)

    try:
        containers = client.containers.list(all=True)
    except docker.errors.APIError as e:
        print(Fore.RED + f"ERROR: Failed to list containers: {e}" + Style.RESET_ALL)
        sys.exit(1)

    if not containers:
        print(Fore.YELLOW + "No containers found." + Style.RESET_ALL)
        sys.exit(0)

    # Table header
    name_w, status_w, health_w, image_w = 30, 12, 15, 40
    header = (
        f"{'CONTAINER':<{name_w}} "
        f"{'STATUS':<{status_w}} "
        f"{'HEALTH':<{health_w}} "
        f"{'IMAGE':<{image_w}}"
    )
    print(Fore.WHITE + Style.BRIGHT + header + Style.RESET_ALL)
    print(Fore.WHITE + "-" * (name_w + status_w + health_w + image_w + 3) + Style.RESET_ALL)

    # Summary counters
    total = len(containers)
    running = 0
    healthy_count = 0
    unhealthy_count = 0

    for container in sorted(containers, key=lambda c: c.name):
        name = container.name[:name_w]
        status = container.status
        health = get_health_status(container)
        image = container.image.tags[0] if container.image.tags else str(container.image.id[:19])

        if status == "running":
            running += 1
        if health == "healthy":
            healthy_count += 1
        elif health == "unhealthy":
            unhealthy_count += 1

        row = (
            f"{name:<{name_w}} "
            f"{colorize_status(status):<{status_w + 9}} "  # +9 for ANSI codes
            f"{colorize_health(health):<{health_w + 9}} "
            f"{Fore.WHITE}{image}{Style.RESET_ALL}"
        )
        print(row)

    # Summary
    print()
    print(Fore.CYAN + Style.BRIGHT + "--- Summary ---" + Style.RESET_ALL)
    print(f"  Total containers: {Fore.WHITE}{total}{Style.RESET_ALL}")
    print(f"  Running:          {Fore.GREEN}{running}{Style.RESET_ALL}")
    print(f"  Stopped:          {Fore.RED}{total - running}{Style.RESET_ALL}")
    print(f"  Healthy:          {Fore.GREEN}{healthy_count}{Style.RESET_ALL}")
    if unhealthy_count:
        print(f"  Unhealthy:        {Fore.RED}{unhealthy_count}{Style.RESET_ALL}")
    print()


if __name__ == "__main__":
    main()
