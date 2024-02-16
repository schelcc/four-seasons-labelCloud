from typing import Tuple, Union, Optional
from . import Camera
from PyQt5.QtGui import QColor
import logging


Point3D = Tuple[float, float, float]

Rotations3D = Tuple[float, float, float]  # euler angles in degrees

Translation3D = Point3D

Dimensions3D = Tuple[float, float, float]  # length, width, height in meters

Color4f = Tuple[float, float, float, float]  # type alias for type hinting

class Point2D(tuple):
    def __new__(cls, x, y):
        return super(Point2D, cls).__new__(cls, (float(x), float(y)))

    def scale(self, scale:float):
        """Scale the points in the tuple by scale param"""
        return Point2D(self[0]*scale, self[1]*scale)
    
    def __str__(self):
        return f"{self[0], self[1]}"
    
    def __repr__(self):
        return f"({self.__str__()})"

class Point3D(tuple):
    def __new__(cls, x, y, z):
        return super(Point3D, cls).__new__(cls, (x, y, z))
    
    def __str__(self):
        return f"{self[0]},{self[1]},{self[2]}"
    
    def __repr__(self):
        return f"({self.__str__()})"

class PointPairCamera():
    def __init__(self, 
        p3d : Point3D, 
        p2d : Point2D, 
        cam : Camera,
        p2d_true : Optional[Point2D] = None):
        self.p3d = p3d 
        self.p2d = p2d
        self.p2d_true = p2d_true # To hold detransformed pt
        self.cam = cam
        self.data = (self.p3d, self.p2d, self.cam)
        
    def __str__(self):
        if self.p2d_true is not None:
            return f"{self.cam},{self.p3d[0]},{self.p3d[1]},{self.p3d[2]},{self.p2d[0]},{self.p2d[1]},{self.p2d_true[0]},{self.p2d_true[1]}"
        else:
            logging.warning("Returning string of a PointPairCamera which doesn't have a true p2d -- this may be an erroneous read/write")
            return f"{self.cam},{self.p3d[0]},{self.p3d[1]},{self.p3d[2]},{self.p2d[0]},{self.p2d[1]},-1,-1"

    def __repr__(self):
        return f"({self.__str__()})"

    def __iter__(self):
        yield from self.data

class Color3f(tuple):
    def __new__(cls, r, g, b):
        return super(Color3f, cls).__new__(cls, (r, g, b))

    def __repr__(self):
        return "ColorRGB(r={}, g={}, b={})".format(*self)

    @classmethod
    def from_qcolor(cls, color: QColor):
        return cls(color.red() / 255, color.green() / 255, color.blue() / 255)

    @staticmethod
    def to_rgba(color: "Color3f", alpha: float = 1.0) -> Color4f:
        return (*color, alpha)  # type: ignore
