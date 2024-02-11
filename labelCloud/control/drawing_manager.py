import logging
from typing import TYPE_CHECKING, Union, Optional

from ..labeling_strategies import BaseLabelingStrategy

from .base_drawing_manager import BaseDrawingManager
from .bbox_controller import BoundingBoxController

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
        
#        if isinstance(self.drawing_strategy, BaseProjCorrection):
#           world_point = self.pcd_manager.discretize_pt(world_point, replace_color=(1., 1., 1.,))

        if is_temporary:
            self.drawing_strategy.register_tmp_point(world_point)
        else:
#            if isinstance(self.drawing_strategy, BaseProjCorrection):
#                if not self.drawing_strategy.hold_3d():
#                    self.drawing_strategy.register_point(world_point)
            if (
                self.drawing_strategy.is_finished()
            ):  # Register bbox to bbox controller when finished
                self.bbox_controller.add_bbox(self.drawing_strategy.get_bbox())
                self.drawing_strategy.reset()
                self.drawing_strategy = None
