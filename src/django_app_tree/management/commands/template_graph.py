import logging
import re
from pathlib import Path

from django.apps import apps
from django.core.management import BaseCommand

DJANGO_PREFIX = "django."

logger = logging.getLogger("main")


class Command(BaseCommand):
    """
    Generates a map of the relations of (html) templates and their extends / imports (or included js file).
    Should be compiled using the fdp compiler from graphviz (https://graphviz.org/).

    Just copy it into an empty file and run the graphviz (https://graphviz.org/) compiler, e.g. with
    `dot graph.dot -Tpdf -o test.pdf -Kfdp`
    to generate a pdf
    """

    help = """Generates a map of the relations of (html) templates and their extends / imports (or included js file).
    Should be compiled using the fdp compiler from graphviz (https://graphviz.org/).

    Just copy it into an empty file and run the graphviz (https://graphviz.org/) compiler, e.g. with
    `dot graph.dot -Tpdf -o test.pdf -Kfdp`
    to generate a pdf"""

    RE_EXTENDS = re.compile(r"{%\s*extends\s*[\"'](?P<template>[/a-zA-Z._0-9\-]+)[\"']\s*%}")
    RE_INCLUDE = re.compile(r"{%\s*include\s*[\"'](?P<template>[/a-zA-Z._0-9\-]+)[\"']\.*")
    RE_SCRIPT = re.compile(r'<script.*?src="(?P<js>[^"]*)"')
    RE_STATIC = re.compile(r"{%\s+static\s+[\"'](?P<import>[^\"']*)[\"']")

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-subgraphs",
            action="store_true",
            default=False,
            help="Dont draw apps as subgraphs",
        )

        parser.add_argument(
            "--app",
            default=None,
            help="Only analyze templates from the given app",
        )

    def info(self, s):
        self.stdout.write(self.style.WARNING(s))

    def handle(self, *args, **options):
        (
            templates,
            templates_per_app,
            template_extends,
            template_imports,
            template_js,
            apps_and_paths,
            portal_apps,
        ) = self.create_template_tree()

        app_filter = options["app"]

        dot_file = "digraph {\n"

        i = 0
        drawn_templates = set()
        for app, app_templates in templates_per_app.items():
            if app not in portal_apps:
                continue

            if app_filter is not None and app != app_filter:
                continue

            if len(app_templates) == 0:
                continue

            if not options["no_subgraphs"]:
                dot_file += f'  subgraph cluster_{i} {{\n    label="{app}";\n'
            for t in app_templates:
                color = (i % 11) + 1
                props = f'color="/set312/{color}", style=filled'
                if t in template_extends.values():
                    props = 'color="blue" fontcolor="white", style=filled'
                dot_file += f'    "{t}" [ {props} ];\n'
                drawn_templates.add(t)
            if not options["no_subgraphs"]:
                dot_file += "  }\n"
            i += 1
        # Now add edges to show "parency"
        for child, parent in template_extends.items():
            if child not in drawn_templates:
                continue
            dot_file += f'  "{child}" -> "{parent}" [color="blue"];\n'

        # Now add import relations
        for templ, imported_templates in template_imports.items():
            for imported_templ in imported_templates:
                if templ not in drawn_templates:
                    continue
                dot_file += f'  "{templ}" -> "{imported_templ}" [ color="green"];\n'

        # Add Javascript imports
        for templ, js_imports in template_js.items():
            for js in js_imports:
                if templ not in drawn_templates:
                    continue
                dot_file += f'  "{js}" [ color="orange", fontcolor="black", style=filled];\n'
                dot_file += f'  "{templ}" -> "{js}" [ color="orange"];\n'
        dot_file += "  splines=true;\n"
        dot_file += "}"

        self.stdout.write(self.style.SUCCESS("dot file generated successfully:"))
        self.stdout.write("----------------------------------------------------")
        self.stdout.write(dot_file)

    def create_template_tree(self):
        templates = set()
        templates_per_app = {}

        template_extends = {}
        template_imports = {}

        template_js = {}

        apps_and_paths = {}

        portal_apps = set()

        for config in apps.get_app_configs():
            self.info(f"Checking {config.name}")
            templates_per_app[config.name] = set()
            apps_and_paths[config.name] = config.path.split("/")[-1]
            if "apps/" in config.path:
                portal_apps.add(config.name)

            template_folder = Path(config.path).joinpath("templates")
            logger.debug(f"Templates: {template_folder}")
            for path in template_folder.rglob("**/*.html"):
                template_path = str(path.relative_to(template_folder))

                # Fill dicts
                templates.add(template_path)
                templates_per_app[config.name].add(template_path)

                # Check extends using a REGEX
                with open(path) as template_file:
                    template = template_file.read()

                # EXTENDS
                match = self.RE_EXTENDS.match(template)

                if match:
                    parent_template = match.group("template")
                    template_extends[template_path] = parent_template

                # FIND INCLUDES
                for m in re.finditer(self.RE_INCLUDE, template):
                    included_template = m.group("template")
                    if template_path not in template_imports:
                        template_imports[template_path] = set()
                    template_imports[template_path].add(included_template)

                # Find JS Imports
                for m in re.finditer(self.RE_SCRIPT, template):
                    js = m.group("js")
                    if template_path not in template_js:
                        template_js[template_path] = set()

                    # Check if its a static
                    static_match = self.RE_STATIC.match(js)
                    if static_match:
                        js = static_match.group("import")
                    template_js[template_path].add(js)

        return (
            templates,
            templates_per_app,
            template_extends,
            template_imports,
            template_js,
            apps_and_paths,
            portal_apps,
        )
