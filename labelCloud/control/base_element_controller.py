"""
Base class for any subsequent element controllers (bboxes, point pairs, etc.)
""" 

import logging
from typing import TYPE_CHECKING, List, Optional, Callable
from functools import wraps

from .pcd_manager import PointCloudManager
from ..definitions import Mode
from ..model.element import Element 
from .config_manager import config 

if TYPE_CHECKING:
    from ..view.gui import GUI

def has_active_element_decorator(func):
    """ 
    Only execute function if there is an active element
    """
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].has_active_element():
            return func(*args, **kwargs)
        else:
            logging.warning("There is currently no active element")

    return wrapper

class BaseElementController(object):
    STD_SCALING = config.getfloat("LABEL", "std_scaling")
    
    def __init__(self, element_type) -> None:
        self.view : GUI 
        self.pcd_manager : PointCloudManager
        self.element_type : Element = element_type
        self.elements : List[element_type] = []
        self.active_element_id : int = -1
        self.add_element_callbacks : List[Callable] = []
        self.update_active_callbacks : List[Callable] = []

        logging.debug(f"BaseElementControl instantiated | Type: {self.element_type}")
        
        
    def has_active_element(self) -> bool:
        """Check if element controller has an active element"""
        return 0 <= self.active_element_id <= len(self.elements)
    
    def get_active_element(self) -> Optional[Element]:
        """Return active element if it exists, otherwise None"""
        if self.has_active_element():
            return self.elements[self.active_element_id]
        else:
            return None 

    def refresh_element_list(self) -> None:
        """Refresh elements w/ PCD update"""
        pass

    def save(self) -> None:
        """Save element list"""
        pass

    def select_relative_element(self, amount : int) -> None:
        """Change element some amount relative to current. Will not proceed if
        there is no active element"""
        if self.has_active_element() and 0 <= self.active_element_id + amount < len(self.elements):
            self.active_element_id += amount

    def set_view(self, view: "GUI") -> None:
        """Set element controller's gui"""
        self.view = view

    def set_pcd_manager(self, pcd_manager : PointCloudManager) -> None:
        """Set element controller's pcd manager"""
        self.pcd_manager = pcd_manager

    def update_element(self, element_id: int, element: Element) -> None:
        """Update controller's element at index element_id w/ what's given in "element\".
        Ensures consistency with intial element type"""
        if isinstance(element, self.element_type) and (0 <= element_id < len(self.elements)):
            self.elements[element_id] = element
            self.update_element_list()
    
    def delete_element(self, element_id : int) -> None:
        """Delete element at index element_id"""
        if 0 <= element_id <= self.active_element_id:
            del self.elements[element_id]
            if self.active_element_id == element_id:
                self.set_active_element(len(self.elements) - 1)
                
    def delete_current_element(self) -> None:
        """Delete active element"""
        self.delete_element(self.active_element_id)
    
    def deselect_element(self) -> None:
        """Deselect active element"""
        self.active_element_id = -1
        self.update_all()
        self.view.status_manager.set_mode(Mode.NAVIGATION)
        
    def set_active_element(self, element_id : int) -> None:
        """Change active element, unsets active element if index outside of range is requested"""
        if 0 <= element_id < len(self.elements):
            self.active_element_id = element_id
            self.update_all()
        else:
            self.deselect_element()
            
    def register_add_element_callback(self, callback : Callable) -> None:
        """Add an action to be performed whenever an element is added to the list.
        Input functions shouldn't depend on return behavior."""
        self.add_element_callbacks.append(callback) 

    def register_update_active_callback(self, callback : Callable) -> None:
        """Add an action to be performed whenever the active element is changed.
        Input functions shouldn't depend on return behavior."""
        self.update_active_callbacks.append(callback)

    def add_element(self, element : Element) -> None:
        logging.debug("ElementController recieved element add:")
        logging.debug(f"Expected type: {self.element_type}\n\t- Received type: {type(element)}")
        if isinstance(element, self.element_type):
            logging.debug("\t- Element add passed instance check")
            self.elements.append(element)
            self.set_active_element(self.elements.index(element))
            
            # Run add element callbacks
            for func in self.add_element_callbacks:
                func()
            
            
    def set_elements(self, elements: List[Element]) -> None:
        """Sets controller's element list. Checks if every contained element is consistent w/
        initial type"""
        if all([isinstance(x, self.element_type) for x in elements]):
            self.elements = elements
    
    def reset(self) -> None:
        """Deselect active element and clear current element list"""
        self.deselect_element()
        self.set_elements([]) 
    
    def update_all(self) -> None:
        """Update various UI elements associated with the controller"""
        raise NotImplementedError 