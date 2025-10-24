# Linting helper for Trashlab projects

set shell := ["/usr/bin/zsh", "-cu"]

lint-sync:
    ruff check --fix .
    ruff format .


