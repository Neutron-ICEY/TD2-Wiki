import atexit
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools.brand_sets.production import assemble

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / 'ui/editor'
NODE = shutil.which('node')
_temporary = None


def candidate():
    """Build one fresh formal candidate per test process; never consume historical dist."""
    global _temporary
    if _temporary is None:
        (ROOT / 'dist').mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='formal-tests-', dir=ROOT / 'dist')
        output = Path(temporary.name) / 'candidate'
        try:
            subprocess.run([NODE, str(EDITOR / 'production/build.cjs'), str(output)],
                           check=True, capture_output=True, text=True, encoding='utf8')
            assemble(ROOT, output)
        except BaseException:
            temporary.cleanup()
            raise
        atexit.register(temporary.cleanup)
        _temporary = temporary
    return Path(_temporary.name) / 'candidate'
