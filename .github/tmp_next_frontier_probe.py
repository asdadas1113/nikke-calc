from pathlib import Path
import sys, inspect
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calculator import timeline
print('SIGNATURE', inspect.signature(timeline.simulate))
print(inspect.getsource(timeline.simulate)[:5000])
