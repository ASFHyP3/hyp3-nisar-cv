from datetime import datetime
from nisar_cv.__main__ import build_hyp3_nisar_cv_parser, stack_id

RELATIVE_ORBIT = 47
FRAME_NUMBER = 22
ORBIT_DIRECTION = "ASCENDING"

def test_stack_id():
    stack_id_string = f"{RELATIVE_ORBIT}_{ORBIT_DIRECTION[0]}_{FRAME_NUMBER}"
    assert stack_id(stack_id_string) == (RELATIVE_ORBIT, ORBIT_DIRECTION, FRAME_NUMBER)


