from datetime import datetime, timezone


def get_current_datetime() -> str:
    """
    Returns the current datetime as a string in UTC
    """

    now_utc = datetime.now(timezone.utc)
    formatted_time = now_utc.strftime("%m/%d/%Y %H:%M:%S")
    return formatted_time
