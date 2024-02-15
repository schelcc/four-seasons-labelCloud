import logging
from pathlib import Path
from typing import List, Optional

from logdecorator import log_on_start
from ..io.labels import BaseLabelFormat, CentroidFormat, KittiFormat, VerticesFormat, PointMatchRaw
from ..io.labels.config import LabelConfig
from ..definitions.labeling_mode import LabelingMode
from ..model import Element 
from .config_manager import config


def get_label_strategy(export_format: str, label_folder: Path) -> "BaseLabelFormat":
    if LabelConfig().type == LabelingMode.OBJECT_DETECTION:
        if export_format == "vertices":
            return VerticesFormat(label_folder, LabelManager.EXPORT_PRECISION)
        elif export_format == "centroid_rel":
            return CentroidFormat(
                label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=True
            )
        elif export_format == "kitti":
            return KittiFormat(
                label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=True
            )
        elif export_format == "kitti_untransformed":
            return KittiFormat(
                label_folder,
                LabelManager.EXPORT_PRECISION,
                relative_rotation=True,
                transformed=False,
            )
        elif export_format != "centroid_abs":
            logging.warning(
                f"Unknown export strategy '{export_format}'. Proceeding with default (centroid_abs)!"
            )
        return CentroidFormat(
            label_folder, LabelManager.EXPORT_PRECISION, relative_rotation=False
        )
    if LabelConfig().type == LabelingMode.PROJECTION_CORRECTION:
        return PointMatchRaw(label_folder, LabelManager.EXPORT_PRECISION)


class LabelManager(object):
    STD_LABEL_FORMAT = LabelConfig().format
    EXPORT_PRECISION = config.getint("LABEL", "export_precision")

    def __init__(
        self,
        strategy: str = STD_LABEL_FORMAT,
        path_to_label_folder: Optional[Path] = None,
    ) -> None:
        self.label_folder = path_to_label_folder or config.getpath(
            "FILE", "label_folder"
        )
        if not self.label_folder.is_dir():
            self.label_folder.mkdir(parents=True)

        self.label_strategy = get_label_strategy(strategy, self.label_folder)

    def import_labels(self, pcd_path: Path) -> List[Element]:
        try:
            return self.label_strategy.import_labels(pcd_path)
        except KeyError as key_error:
            logging.warning("Found a key error with %s in the dictionary." % key_error)
            logging.warning(
                "Could not import labels, please check the consistency of the label format."
            )
            return []
        except AttributeError as attribute_error:
            logging.warning(
                "Attribute Error: %s. Expected a dictionary." % attribute_error
            )
            logging.warning(
                "Could not import labels, please check the consistency of the label format."
            )
            return []

    def export_labels(self, pcd_path: Path, elements: List[Element]) -> None:
        self.label_strategy.export_labels(elements, pcd_path)
