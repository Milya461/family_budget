"""
Legacy entry point.

The production application runs through
Cloudflare Workers using worker.py.

This file is intentionally kept without
database initialization or polling logic.
"""


def main():
    raise RuntimeError(
        "The bot is deployed as a Cloudflare Worker. "
        "Use worker.py instead of main.py."
    )


if __name__ == "__main__":
    main()
