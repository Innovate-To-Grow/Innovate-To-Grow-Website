"""Working out what each row of a sheet would do, without writing anything: which member a row means
(``resolution``), the row analysis (``rows``), the choices a review offers (``choices``, ``conflict_choices``), how
rows compare (``grouping``), risky changes (``risky``) and the plain sentences of a review (``describe``)."""

from .describe import PRECEDENCE, conflict_code, conflict_title, describe_action, why
from .resolution import (
    INVALID,
    NEEDS_DECISION,
    NO_CHANGE,
    READY_CREATE,
    READY_UPDATE,
    SKIP_EXISTING,
    UPDATE_EXISTING,
    Context,
    Resolution,
    resolve_row,
    suggested_action,
)
from .rows import RowAnalysis, analyse_rows, update_targets
