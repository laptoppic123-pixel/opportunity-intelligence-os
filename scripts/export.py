from opportunity_intelligence.cli import main
import sys

if __name__ == "__main__":
    flags = [a for a in sys.argv[1:] if a in {"--demo", "--live"}]
    remaining = [a for a in sys.argv[1:] if a not in {"--demo", "--live"}]
    sys.argv = [sys.argv[0], *flags, "export", *remaining]
    raise SystemExit(main())
