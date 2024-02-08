from enum import IntEnum

class Camera(IntEnum):
    """Which camera a 2d point corresponds to"""
    
    LEFT = 0
    MIDDLE = 1
    RIGHT = 2