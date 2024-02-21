import logging
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ..view.gui import GUI

from ..definitions.types import Point2D, Point3D, PointPairCamera
from ..definitions.cameras import Camera
from ..labeling_strategies import BaseLabelingStrategy
from ..proj_correction_strategies import BaseProjCorrection

from .bbox_controller import BoundingBoxController
from .manual_calibration_controller import ProjectionCorrectionController

 
class BaseDrawingManager(object):
    def __init__(self, drawing_strategy_type) -> None:
        self.view: "GUI"
        self.drawing_strategy_type = drawing_strategy_type
        self.drawing_strategy = None
        
    def set_view(self, view: "GUI") -> None:
        self.view = view
        self.view.gl_widget.drawing_mode = self
    
    def is_active(self) -> bool:
        return self.drawing_strategy is not None and isinstance(
            self.drawing_strategy, self.drawing_strategy_type
        )    
        
    def has_preview(self) -> bool:
        if self.is_active():
            return self.drawing_strategy.__class__.PREVIEW
        return False
    
    def set_drawing_strategy(self, strategy) -> None:
        if self.is_active() and self.drawing_strategy == strategy:
            self.reset()
            logging.info("Deactivated drawing!")
        else:
            if self.is_active():
                self.reset()
                logging.info("Reset previous active drawing mode!")
                
            self.drawing_strategy = strategy
        
    def draw_preview(self) -> None:
        if self.drawing_strategy is not None:
            self.drawing_strategy.draw_preview()
    
    def reset(self, points_only : bool = False) -> None:
        if self.is_active():
            self.drawing_strategy.reset()
            self.drawing_strategy = None
    
    def register_point_3d(self, p3d : Point3D) -> None:
        """Register point in pointcloud. Does nothing by default"""
        pass

    def register_point_2d(self, p2d : Point2D, cam : Camera) -> None:
        """Register point in image. Does nothing by default"""
        pass

