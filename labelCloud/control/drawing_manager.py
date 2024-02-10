import logging
from typing import TYPE_CHECKING, Union

from ..labeling_strategies import BaseLabelingStrategy
from ..proj_correction_strategies import BaseProjCorrection
from .bbox_controller import BoundingBoxController

from .pcd_manager import PointCloudManger

if TYPE_CHECKING:
    from ..view.gui import GUI


class DrawingManager(object):
    def __init__(self, bbox_controller: BoundingBoxController, pcd_manager: PointCloudManger) -> None:
        self.view: "GUI"
        self.bbox_controller = bbox_controller
        self.drawing_strategy: Union[BaseLabelingStrategy, BaseProjCorrection, None] = None
        self.pcd_manager: PointCloudManger = pcd_manager

    def set_view(self, view: "GUI") -> None:
        self.view = view
        self.view.gl_widget.drawing_mode = self

    def is_active(self) -> bool:
        return self.drawing_strategy is not None and isinstance(
            self.drawing_strategy, (BaseLabelingStrategy, BaseProjCorrection)
        )

    def has_preview(self) -> bool:
        if self.is_active():
            return self.drawing_strategy.__class__.PREVIEW  # type: ignore
        return False

    def set_drawing_strategy(self, strategy: Union[BaseProjCorrection, BaseLabelingStrategy]) -> None:
        if self.is_active() and self.drawing_strategy == strategy:
            self.reset()
            logging.info("Deactivated drawing!")
        else:
            if self.is_active():
                self.reset()
                logging.info("Resetted previous active drawing mode!")

            self.drawing_strategy = strategy

    def register_point(
        self, x: float, y: float, correction: bool = False, is_temporary: bool = False
    ) -> None:
        assert self.drawing_strategy is not None
        world_point = self.view.gl_widget.get_world_coords(x, y, correction=correction)
        
        if isinstance(self.drawing_strategy, BaseProjCorrection):
            world_point = self.pcd_manager.discretize_pt(world_point, replace_color=(1., 1., 1.,))

        if is_temporary:
            self.drawing_strategy.register_tmp_point(world_point)
        else:
            if isinstance(self.drawing_strategy, BaseProjCorrection):
                if not self.drawing_strategy.hold_3d():
                    self.drawing_strategy.register_point(world_point)
            elif (
                self.drawing_strategy.is_finished()
            ):  # Register bbox to bbox controller when finished
                self.bbox_controller.add_bbox(self.drawing_strategy.get_bbox())
                self.drawing_strategy.reset()
                self.drawing_strategy = None

    def draw_preview(self) -> None:
        if self.drawing_strategy is not None:
            self.drawing_strategy.draw_preview()

    def reset(self, points_only: bool = False) -> None:
        if self.is_active():
            self.drawing_strategy.reset()  # type: ignore
            if not points_only:
                self.drawing_strategy = None
