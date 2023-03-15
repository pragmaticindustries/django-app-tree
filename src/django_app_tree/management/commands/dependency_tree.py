import importlib
import inspect
import logging
from pathlib import Path

from django.apps import AppConfig, apps
from django.core.management import BaseCommand
from django.db.models.fields.related import ForeignObject

DJANGO_PREFIX = "django."

logger = logging.getLogger("main")


class Command(BaseCommand):
    """
    Generates a dependency tree between APPS.
    The Final output is a graphviz file between the "-----------" lines
    Just copy it into an empty file and run the graphviz (https://graphviz.org/) compiler, e.g. with
    `dot dependencies.dot -Tpdf -o test.pdf`
    to generate a pdf
    """

    help = """Generates a dependency tree between APPS.
    The Final output is a graphviz file between the "-----------" lines
    Just copy it into an empty file and run the graphviz (https://graphviz.org/) compiler, e.g. with
    `dot dependencies.dot -Tpdf -o test.pdf`
    to generate a pdf"""

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-imports",
            action="store_true",
            default=False,
            help="Skip dependencies via imports",
        )

        parser.add_argument(
            "--with-labels",
            action="store_true",
            default=False,
            help="Add Labels on Graph",
        )

        parser.add_argument(
            "--from-app",
            default=None,
            help="show dependencies of the given app",
        )

        parser.add_argument(
            "--to-app",
            default=None,
            help="show apps that depend on the given app",
        )

        parser.add_argument(
            "--contains-app",
            default=None,
            help="show dependencies that have the given app as from OR to",
        )

    def info(self, s):
        self.stdout.write(self.style.WARNING(s))

    def handle(self, *args, **options):
        (
            portal_apps,
            app_relations_by_models,
            app_relations_by_imports,
            models_in_apps,
            imports_in_apps,
        ) = self.create_module_tree()

        if options["contains_app"] and (options["from_app"] or options["to_app"]):
            self.stdout.write(self.style.NOTICE("If --contains-app is set, than from / to app cannot be set!"))
            return

        if options["contains_app"]:
            self.stdout.write(self.style.SUCCESS(f"Filtering dependencies that contain {options['contains_app']}"))

            new_app_relations_by_models = {
                a: b for a, b in app_relations_by_models.items() if a == options["contains_app"]
            }

            for a, b in app_relations_by_models.items():
                if a not in new_app_relations_by_models:
                    new_app_relations_by_models[a] = set()
                for c in b:
                    if c == options["contains_app"]:
                        new_app_relations_by_models[a].add(c)

            app_relations_by_models = new_app_relations_by_models

            new_app_relations_by_imports = {
                a: b for a, b in app_relations_by_imports.items() if a == options["contains_app"]
            }

            for a, b in app_relations_by_imports.items():
                if a not in new_app_relations_by_imports:
                    new_app_relations_by_imports[a] = set()
                for c in b:
                    if c == options["contains_app"]:
                        new_app_relations_by_imports[a].add(c)

            app_relations_by_imports = new_app_relations_by_imports

        if options["from_app"]:
            # filter
            self.stdout.write(self.style.SUCCESS(f"Filtering dependencies to {options['from_app']}"))
            app_relations_by_models = {a: b for a, b in app_relations_by_models.items() if a == options["from_app"]}
            app_relations_by_imports = {a: b for a, b in app_relations_by_imports.items() if a == options["from_app"]}

        if options["to_app"]:
            # filter
            self.stdout.write(self.style.SUCCESS(f"Filtering dependencies to {options['to_app']}"))
            app_relations_by_models = {
                a: {c for c in b if c == options["to_app"]} for a, b in app_relations_by_models.items()
            }
            app_relations_by_imports = {
                a: {c for c in b if c == options["to_app"]} for a, b in app_relations_by_imports.items()
            }

        dot_file = self.create_dot_file(
            portal_apps,
            app_relations_by_models,
            app_relations_by_imports,
            models_in_apps,
            imports_in_apps,
            options["skip_imports"],
            options["with_labels"],
        )

        self.stdout.write(self.style.SUCCESS("dot file generated successfully:"))
        self.stdout.write("----------------------------------------------------")
        self.stdout.write(dot_file)
        self.stdout.write("----------------------------------------------------")

    def create_module_tree(self):
        app_relations_by_models = {}
        app_relations_by_imports = {}

        models_in_apps = {}
        imports_in_apps = {}

        # store a list of all Model Classes
        models_in_apps = {}

        apps_and_paths = {}

        portal_apps = set()

        for config in apps.get_app_configs():
            self.info(f"Checking {config.name}")
            app_relations_by_models[config.name] = set()
            apps_and_paths[config.name] = config.path.split("/")[-1]
            if "apps/" in config.path:
                portal_apps.add(config.name)
            for model in config.get_models():
                logger.debug(f" - Checking Model {model}")
                models_in_apps[model] = config.name
                for related in model._meta.related_objects:
                    # print(f"   --> {related}")
                    related_config = related.related_model._meta.app_config
                    if config != related_config:
                        logger.debug(f"!! Is used by APP: {related_config.name} !!")
                for field in model._meta.fields:
                    # Find dependant modules
                    if isinstance(field, ForeignObject):
                        related_config = field.related_model._meta.app_config
                        if config != related_config:
                            logger.debug(f"!! USES APP: {related_config.name} !!")
                            app_relations_by_models[config.name].add(related_config.name)

                            edge = (config.name, related_config.name)
                            if edge not in models_in_apps:
                                models_in_apps[edge] = set()
                            models_in_apps[edge].add(field.related_model.__name__)

        # Now iterate all .py files to see if they load a certain model class
        for config in apps.get_app_configs():
            config: AppConfig
            app_relations_by_imports[config.name] = set()
            self.info(f"Checking {config.name} / {config.path}")
            # print(f"Path: {config.path}")
            # Recursively find all files
            prefix = config.path.split("/")[-1]
            for path in Path(config.path).rglob("*.py"):
                if "test" in path.name:
                    continue
                # print(f" -> {path.name}")
                module_name = prefix + "." + path.name.replace(config.path, "").replace(".py", "").replace("/", ".")
                # print(f" --> {module_name}")
                deps, app_imports = self.get_dependent_modules_via_import(apps_and_paths, module_name)

                for dep in deps:
                    if dep != config.name:
                        app_relations_by_imports[config.name].add(dep)

                        edge = (config.name, dep)
                        if edge not in imports_in_apps:
                            imports_in_apps[edge] = set()

                        imports = app_imports.get(dep)
                        if imports:
                            for imp in imports:
                                imports_in_apps[edge].add(imp)

        logger.debug("!!! Dependency Tree !!!")
        logger.debug(app_relations_by_models)
        logger.debug("!!! Dependency Tree !!!")
        logger.debug(app_relations_by_imports)

        return (
            portal_apps,
            app_relations_by_models,
            app_relations_by_imports,
            models_in_apps,
            imports_in_apps,
        )

    def create_dot_file(
        self,
        portal_apps,
        app_relations_by_models,
        app_relations_by_imports,
        models_in_apps,
        imports_in_apps,
        skip_imports,
        with_labels,
    ):
        # Create Graphviz Code
        dot = "digraph dependencies {\n  overlap=false;\n\n"
        for app, relations in app_relations_by_models.items():
            app: str
            # skip django
            if app.startswith(DJANGO_PREFIX):
                continue
            for rel in relations:
                props = ""

                if rel != "portal_core":
                    props = 'color="red" fontcolor="red"'
                if rel.startswith(DJANGO_PREFIX):
                    props = 'color="blue" fontcolor="blue"'

                # Add thickness
                weight = 1.0

                if models_in_apps.get((app, rel)):
                    weight = len(models_in_apps.get((app, rel)))

                props += f' penwidth="{weight}"'

                if with_labels and models_in_apps.get((app, rel)):
                    props += f' label="{", ".join(models_in_apps.get((app, rel)))}"'
                dot += f'  "{app}" -> "{rel}" [ {props} ]\n'

        # Imports loaded
        if skip_imports:
            self.stdout.write(self.style.NOTICE("Dependencies via imports are skipped!"))
        else:
            for app, relations in app_relations_by_imports.items():
                app: str
                # skip djang
                if app.startswith(DJANGO_PREFIX):
                    continue
                for rel in relations:
                    if app in portal_apps and rel in portal_apps:
                        weight = 1.0

                        if imports_in_apps.get((app, rel)):
                            weight = len(imports_in_apps.get((app, rel)))

                        props = f'color="orange" fontcolor="orange" penwidth={weight}'

                        if with_labels and imports_in_apps.get((app, rel)):
                            props += f' label="{", ".join(imports_in_apps.get((app, rel)))}"'
                    else:
                        continue
                    dot += f'  "{app}" -> "{rel}" [ {props} ]\n'

        dot += "}\n"

        return dot

    @staticmethod
    def get_dependent_modules_via_import(apps_and_paths, module_path):
        print(f"Checking Module: {module_path}")

        imports_per_app = {}

        dependencies = set()
        try:
            module = importlib.import_module(module_path)

            # Inspect
            for member in inspect.getmembers(module):
                if inspect.isclass(member[1]) or inspect.isfunction(member[1]):
                    clazz_or_func = member[1]
                    if clazz_or_func.__module__ != module_path:
                        print(f"Dependency on {clazz_or_func} ({clazz_or_func.__module__})")
                        for app, path in apps_and_paths.items():
                            if clazz_or_func.__module__.startswith(path):
                                dependencies.add(app)

                                if app not in imports_per_app:
                                    imports_per_app[app] = set()

                                imports_per_app[app].add(clazz_or_func.__name__)
        except ModuleNotFoundError:
            pass

        return dependencies, imports_per_app
