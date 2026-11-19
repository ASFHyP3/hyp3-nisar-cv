import pytest

from nisar_cv.__main__ import stack_id


def test_stack_id():
    RELATIVE_ORBIT = 47
    FRAME_NUMBER = 22
    ORBIT_DIRECTION = "ASCENDING"
    stack_id_string = f"{RELATIVE_ORBIT}_{ORBIT_DIRECTION[0]}_{FRAME_NUMBER}"
    assert stack_id(stack_id_string) == (RELATIVE_ORBIT, ORBIT_DIRECTION, FRAME_NUMBER)


def test_invalid_relative_orbit():
    RELATIVE_ORBIT = 0
    FRAME_NUMBER = 22
    ORBIT_DIRECTION = "ASCENDING"
    stack_id_string = f"{RELATIVE_ORBIT}_{ORBIT_DIRECTION[0]}_{FRAME_NUMBER}"
    with pytest.raises(AssertionError):
        stack_id(stack_id_string)


def test_invalid_frame_number():
    RELATIVE_ORBIT = 47
    FRAME_NUMBER = 0
    ORBIT_DIRECTION = "ASCENDING"
    stack_id_string = f"{RELATIVE_ORBIT}_{ORBIT_DIRECTION[0]}_{FRAME_NUMBER}"
    with pytest.raises(AssertionError):
        stack_id(stack_id_string)
