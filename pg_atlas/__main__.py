"""Allow `python -m pg_atlas` invocation."""
from pg_atlas.cli import main
import sys

sys.exit(main())
