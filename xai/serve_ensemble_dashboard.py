#!/usr/bin/env python3
"""Compatibility command: serves the selected adaptive federated global model."""
if __package__:
    from .serve_dashboard import main
else:
    from serve_dashboard import main

if __name__ == "__main__":
    main()
