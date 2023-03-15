import json
import logging
import os
import re
from pathlib import Path

from django.apps import apps
from django.apps.config import AppConfig
from django.core.management import BaseCommand

DJANGO_PREFIX = "django."

logger = logging.getLogger("main")


class Command(BaseCommand):
    """
    Command to find out which of the INSTALLED_APPS was installed with which pip-package.
    Therefore it checks all installed (pip) packages and merges it with the INSTALLED_APPS.
    Final output is a list of all the apps with the pip packages they were installed from
    and a list of apps that were not installed via pip (so they e.g. have to be part of the repo).
    """

    help = """Command to find out which of the INSTALLED_APPS was installed with which pip-package.
    Therefore it checks all installed (pip) packages and merges it with the INSTALLED_APPS.
    Final output is a list of all the apps with the pip packages they were installed from
    and a list of apps that were not installed via pip (so they e.g. have to be part of the repo).
    """

    RE_PIP_LINE = re.compile(r"^(?P<package>[a-zA-Z0-9_.\-]+)==(?P<version>[a-z0-9.]+)$")

    def handle(self, *args, **options):
        apps_and_paths = {}
        apps_and_packages = {}
        packages_and_paths = {}
        packages_by_name = {}

        for config in apps.get_app_configs():
            config: AppConfig
            print(f"{config.name} -> {config.path}")
            apps_and_paths[config.name] = config.path

        freeze_output = os.popen("pip list -v --format json")

        output_json = freeze_output.read()
        freeze_output.close()

        pip_packages = json.loads(output_json)

        n_pkg = len(pip_packages)
        i = 1
        for pkg in pip_packages:
            # print(f"Package: {pkg.get('name')} / {pkg.get('version')} -> {pkg.get('location')}")

            print(f"{i}/{n_pkg}")
            i += 1

            packages_by_name[pkg.get("name")] = pkg

            search_paths = set()

            # if pkg_path.exists():
            #     search_paths.add(pkg_path)
            # else:
            show_output = os.popen(f"pip show -f {pkg.get('name')}")
            paths = set()
            found_files = False
            for line in show_output.readlines():
                if line == "Files:\n":
                    found_files = True
                    continue
                if found_files:
                    file_path = line.strip(" ")[:-1]
                    if "/" in file_path:
                        path_only = "/".join(file_path.split("/")[:-1])
                        paths.add(path_only)
            show_output.close()

            for p in paths:
                p: str
                segments = p.split("/")
                for seg_cnt in range(0, len(segments)):
                    subpath = "/".join(segments[0 : (seg_cnt + 1)])
                    search_paths.add(Path(pkg.get("location")).joinpath(subpath))

            packages_and_paths[pkg.get("name")] = {str(p) for p in search_paths}

            # Now check if a django app is in here
            for n, p in apps_and_paths.items():
                p: Path
                for sp in search_paths:
                    try:
                        # This will throw an exception if its NOT relative
                        Path(p).relative_to(sp)
                        # So this line is only executed if it is...
                        apps_and_packages[n] = pkg.get("name")
                    except ValueError:
                        pass

        all_apps = set(apps_and_paths.keys())
        for app, pkg in apps_and_packages.items():
            print(f"{app} -> {pkg} (version = {packages_by_name.get(pkg).get('version')})")
            all_apps.remove(app)

        print("Apps without a module:")

        for app in all_apps:
            print(f" - {app}")

        # print(json.dumps({a:list(b) for a,b in packages_and_paths.items()}))
