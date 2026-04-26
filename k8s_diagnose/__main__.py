"""k8s-diagnose entry point."""
import sys


def main():
    from k8s_diagnose.cli import app
    app()


if __name__ == "__main__":
    main()
