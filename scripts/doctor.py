from opportunity_intelligence.cli import main
import sys

if __name__ == "__main__":
    sys.argv = [sys.argv[0], *sys.argv[1:], "doctor"]
    raise SystemExit(main())
