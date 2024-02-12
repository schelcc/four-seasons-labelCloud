import logging
from typing import TYPE_CHECKING, Union, Optional

from ..labeling_strategies import BaseLabelingStrategy
from ..proj_correction_strategies import BaseProjCorrection

from .base_drawing_manager import BaseDrawingManager
from .bbox_controller import BoundingBoxController
from .projection_controller import ProjectionCorrectionController
from .pcd_manager import PointCloudManager
from ..definitions import Camera

if TYPE_CHECKING:
    from ..view.gui import GUI


class LabelDrawingManager(BaseDrawingManager):
    def __init__(self, bbox_controller : BoundingBoxController) -> None:
        super().__init__(BaseLabelingStrategy)
        self.bbox_controller = bbox_controller
        self.drawing_strategy: Optional[BaseLabelingStrategy] = None

    def register_point(
        self, x: float, y: float, correction: bool = False, is_temporary: bool = False
    ) -> None:
        assert self.drawing_strategy is not None
        world_point = self.view.gl_widget.get_world_coords(x, y, correction=correction)
        
        if is_temporary:
            self.drawing_strategy.register_tmp_point(world_point)
        else:
            self.drawing_strategy.register_point(world_point)
            if (
                self.drawing_strategy.is_finished()
            ):  # Register bbox to bbox controller when finished
                self.bbox_controller.add_bbox(self.drawing_strategy.get_bbox())
                self.drawing_strategy.reset()
                self.drawing_strategy = None

class ProjectionDrawingManager(BaseDrawingManager):
    def __init__(self, point_controller : ProjectionCorrectionController, pcd_manager : PointCloudManager):
        super().__init__(BaseProjCorrection)
        self.point_controller = point_controller
        self.drawing_strategy: Optional[BaseProjCorrection] = None
        self.pcd_manager = pcd_manager

    def register_point_3d(
        self, x: float, y: float, correction: bool = False, is_temporary: bool = False 
    ) -> None:
        if self.drawing_strategy is None:
            return
        
        world_point = self.view.gl_widget.get_world_coords(x, y, correction=correction)
        world_point = self.pcd_manager.discretize_pt(world_point, replace_color=(1., 1., 1.,))
        
        if is_temporary:
            self.drawing_strategy.register_tmp_point(world_point)
        else:
            self.drawing_strategy.register_point(world_point)
            
        if self.drawing_strategy.is_finished():
            self.finish() 

    def register_point_2d(
        self, x: float, y: float, camera: Camera
    ) -> None:
        if self.drawing_strategy is None:
            return None
        
        self.drawing_strategy.register_point_2d((x, y), camera) 
        if (self.drawing_strategy.is_finished()):
            self.finish()

    def finish(self) -> None:
        if self.drawing_strategy is not None:
            self.point_controller.add_point(self.drawing_strategy.get_complete_point())
            self.drawing_strategy = None