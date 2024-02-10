from enum import IntEnum

class Camera(IntEnum):
    """Which camera a 2d point corresponds to.
    Left : 0
    Middle : 1
    Right : 2"""
    
    LEFT = 0
    MIDDLE = 1
    RIGHT = 2