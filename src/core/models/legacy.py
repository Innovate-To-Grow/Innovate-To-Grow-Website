from .managers import ProjectControlManager
from .versioning import ProjectControlModel


# Legacy aliases for backward compatibility
TimeStampedModel = ProjectControlModel
UUIDModel = ProjectControlModel
SoftDeleteModel = ProjectControlModel
SoftDeleteManager = ProjectControlManager
