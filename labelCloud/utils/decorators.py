from functools import wraps

from ..control.config_manager import config

def in_labeling_only_decorator(func):
    """
    Only execute function in labeling usage mode
    """
   
    @wraps(func)
    def wrapper(*args, **kwargs):
        if config.get("FILE", "usage_mode") == "label":
            return func(*args, **kwargs)
        
    return wrapper

def in_projection_only_decorator(func):
    """ 
    Only execute in projection usage mode
    """
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        if config.get("FILE", "usage_mode") == "projection":
            return func(**args, **kwargs)
        
    return wrapper