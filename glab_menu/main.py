from pathlib import Path
import yaml
from pydantic import BaseModel
import sys
import gitlab
import subprocess
from datetime import datetime, timedelta
import re

SCRIPT_PATH = sys.argv[0]

CONFIG_DIRECTORY = Path.home() / ".config" / "glab-menu"
CONFIG_FILE = CONFIG_DIRECTORY / "config.yaml"

CACHE_DIRECTORY = Path.home() / ".cache" / "glab-menu"
CACHE_FILE = CACHE_DIRECTORY / "cache.yaml"


class AppConfig(BaseModel):
    token: str
    host: str = "https://gitlab.com"
    org: str


def read_config() -> AppConfig:
    # Ensure the config directory exists
    CONFIG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    # Ensure the config file exists
    if not CONFIG_FILE.exists():
        raise ValueError(f"Config file {CONFIG_FILE} does not exist")
    with open(CONFIG_DIRECTORY / "config.yaml", "r") as f:
        config_in_file = yaml.safe_load(f)
    return AppConfig(**config_in_file)


class CachedProject(BaseModel):
    id: int
    path_with_namespace: str
    name: str
    description: str | None


class AppCache(BaseModel):
    projects: list[CachedProject]
    last_updated: datetime

    @property
    def is_stale(self) -> bool:
        return datetime.now() - self.last_updated > timedelta(days=7)


def read_cache():
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    if not CACHE_FILE.exists():
        return AppCache(projects=[], last_updated=datetime.min)
    with open(CACHE_FILE, "r") as f:
        return AppCache(**yaml.safe_load(f))


def update_cache(projects):
    cached_projects = []
    for project in projects.list(iterator=True):
        cached_projects.append(
            CachedProject(
                id=project.id,
                path_with_namespace=project.path_with_namespace,
                name=project.name,
                description=project.description,
            )
        )
    new_cache = AppCache(projects=cached_projects, last_updated=datetime.now())
    with open(CACHE_FILE, "w") as f:
        yaml.safe_dump(new_cache.model_dump(), f)
    return new_cache


def notify_send(title: str, message: str, level: str | None = None) -> None:
    print(f"{title}: {message}")
    command = f"notify-send -a glab-menu '{title}' '{re.escape(message)}'" + (
        f" -u {level}" if level else ""
    )
    print("hey")
    print(command)
    subprocess.call(command, shell=True)


def show_menu():
    try:
        config = read_config()
    except ValueError as e:
        print(e)
        sys.exit(1)

    cache = read_cache()

    if cache.is_stale:
        notify_send("Updating cache", "GitLab project cache is stale, updating now")
        gl = gitlab.Gitlab(config.host, private_token=config.token)
        gl.auth()
        org = gl.groups.get(config.org)
        update_cache(org.projects)
        notify_send("Cache updated", "GitLab project cache updated, ready to go")
        return

    try:
        wofi_result = subprocess.check_output(
            f"{SCRIPT_PATH} list | wofi --allow-markup --show dmenu --prompt 'GitLab Projects' --lines 10",
            shell=True,
        )
    except subprocess.CalledProcessError:
        sys.exit(1)

    chosen_project = wofi_result.decode().strip()
    if not chosen_project:
        sys.exit(0)

    open_project(chosen_project)


def get_project_list():
    cache = read_cache()
    for project in sorted(cache.projects, key=lambda x: x.path_with_namespace):
        if project.description and False:
            print(f"{project.path_with_namespace}: {project.description}")
        else:
            print(project.path_with_namespace)


def open_project(path_with_namespace: str):
    config = read_config()
    path = config.host + "/" + path_with_namespace
    subprocess.call(f"xdg-open {path}", shell=True)


def main():
    try:
        command = sys.argv[1]
    except IndexError:
        show_menu()
        return

    match command:
        case "list":
            get_project_list()
        case "open":
            open_project(sys.argv[2])
