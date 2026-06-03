class Config():
    # Static page-rendering site: no sessions, flash, CSRF, or forms — so no
    # SECRET_KEY is needed. Only the response cache remains.
    CACHE_TYPE = "simple"
    CACHE_DEFAULT_TIMEOUT = 300
