# django-app-tree

This is a dependency checking / generating tool that highlights dependencies between apps.

One type of dependency is that models from app A have a reference to a model in app B.

Another one is simply where code is called.

The tool is a Django management command that can simply be called by

```
./manage.py dependency_tree
```

especially

```
./manage.py dependency_tree --help
```

might be helpful.

The final output is a graphviz file between the "-----------" lines

Just copy it into an empty file and run the graphviz (https://graphviz.org/) compiler, e.g. with `dot dependencies.dot -Tpdf -o test.pdf` to generate a PDF.

Example commands are:

```
./manage.py dependency_tree --contains-app=test --with-labels
```

to show all relations of the "test" app (from / to) and add the name of the models, functions or classes as labels.

Or:

```
./manage.py dependency_tree --from-app=example --with-labels
```

to show which apps the "example" app calls code from.

To get the full picture of all relations, just call:

```
./manage.py dependency_tree --with-labels
```

BUT beware... you might not like what you see :)