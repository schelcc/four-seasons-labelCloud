from enum import IntEnum
from typing import List

LEFT = 0
MIDDLE = 1
RIGHT = 2

class Camera:
    """Which camera a 2d point corresponds to.
    Left : 0
    Middle : 1
    Right : 2"""

    SELECTER : List[str] = ["left", "middle", "right"]
    
    def __init__(self, cam : int):
        self.cam : int = cam 

    def __str__(self):
        return self.SELECTER[self.cam] 

    def __repr__(self):
        return self.__str__()