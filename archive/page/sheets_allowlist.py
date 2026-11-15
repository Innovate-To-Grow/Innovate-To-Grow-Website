import urllib.parse

# Only the spreadsheets the archived pages actually use — keeps the proxy from
# being an open relay that lets anyone spend this key's quota.
ALLOWED_SPREADSHEETS = frozenset(
    {
        "1-p5yXTpgRKfbxVBuvehR8PPoxKCMRrHC_yXMfNNYB0E",
        "10_l1AyeiwCN8GZl6CfL6CwOwVH6K66zmrZd1xxVx7qk",
        "1188BQGCadaysxPN7VkVdcFeLhOi4zbwDVWdeMCcQQB4",
        "13Yds-sPSPjLSWYyCyIaHauTZ3lchGiNH1n-II6tJOMM",
        "19VoMJrwiybqCNlepCa6QTBYIx5mqzZBVeOcPNxNvLnc",
        "1AoW60T0IHSkqO4dUzYV6ErWxMHKOhg73NpddUc2ZUxM",
        "1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc",
        "1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo",
        "1fLRbUOkzH1YJhsuV49tiQf0ahXa2U3TrekE8FJgdzOM",
        "1L3fgZFAWnwXbRqn2Gt8Qf14-MCGxB46KZ3lfWe1a5ps",
        "1MfFpZ0mn90UkqEuegBWopPqucfkmzzUWNl0oR2eSWdo",
        "1nqwEiLllm2wsL0SUUSIdT8nqspEMLFP41wtC-akKASE",
        "1NvgPCISxxyoi_GjM77lb2RPhaAqtulA7YA0-1DnwMSk",
        "1NYKJkIAlAqMQyXLZroqEfm4T5jnafj7ksTl66j-H_Kg",
        "1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik",
        "1TJZfQFYf0iw1SBcqrdnS_efOsFzIppMg1aOajE-atc4",
        "1VF29jHnlXbl02BK6_GPv91hADGM_QsvvM_SgH2X8Ohs",
        "1WuiISEzbd0VCeB6F9cdR3dYFsZoFHwV6GWPH9iYYKQQ",
        "1XA1WXfZyZ1GzaEmmCY5RNuHM-q1WEuAQ89vSuepJtp8",
    }
)


ALLOWED_SHEET_RANGES = frozenset(
    {
        ("1-p5yXTpgRKfbxVBuvehR8PPoxKCMRrHC_yXMfNNYB0E", "2024-01-Spring-I2G-WEB"),
        ("10_l1AyeiwCN8GZl6CfL6CwOwVH6K66zmrZd1xxVx7qk", "2021-01-Spring-I2G-WEB"),
        ("1188BQGCadaysxPN7VkVdcFeLhOi4zbwDVWdeMCcQQB4", "A1:Y76"),
        ("13Yds-sPSPjLSWYyCyIaHauTZ3lchGiNH1n-II6tJOMM", "2022-01-Spring-I2G-WEB"),
        ("19VoMJrwiybqCNlepCa6QTBYIx5mqzZBVeOcPNxNvLnc", "I2G-Tracks"),
        ("1AoW60T0IHSkqO4dUzYV6ErWxMHKOhg73NpddUc2ZUxM", "2023-01-Spring-I2G-WEB"),
        ("1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc", "I2G-Tracks"),
        ("1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo", "2021-01-Fall-I2G-WEB"),
        ("1fLRbUOkzH1YJhsuV49tiQf0ahXa2U3TrekE8FJgdzOM", "2023-08-Fall-I2G-WEB"),
        ("1L3fgZFAWnwXbRqn2Gt8Qf14-MCGxB46KZ3lfWe1a5ps", "I2G-Tracks"),
        ("1MfFpZ0mn90UkqEuegBWopPqucfkmzzUWNl0oR2eSWdo", "I2G-Tracks"),
        ("1nqwEiLllm2wsL0SUUSIdT8nqspEMLFP41wtC-akKASE", "I2G-Tracks"),
        ("1NvgPCISxxyoi_GjM77lb2RPhaAqtulA7YA0-1DnwMSk", "I2G-WEB"),
        ("1NYKJkIAlAqMQyXLZroqEfm4T5jnafj7ksTl66j-H_Kg", "I2G-Tracks"),
        ("1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik", "2025-I2G2-Tracks"),
        ("1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik", "A1:Y76"),
        ("1TJZfQFYf0iw1SBcqrdnS_efOsFzIppMg1aOajE-atc4", "Sheet1"),
        ("1VF29jHnlXbl02BK6_GPv91hADGM_QsvvM_SgH2X8Ohs", "I2G-tracks"),
        ("1WuiISEzbd0VCeB6F9cdR3dYFsZoFHwV6GWPH9iYYKQQ", "I2G-Tracks"),
        ("1XA1WXfZyZ1GzaEmmCY5RNuHM-q1WEuAQ89vSuepJtp8", "2022-08-Fall-I2G-WEB"),
    }
)


UPSTREAM = "https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{cell_range}"


TRUSTED_SHEET_URLS = {
    (sheet_id, cell_range): UPSTREAM.format(
        sheet_id=sheet_id,
        cell_range=urllib.parse.quote(cell_range, safe=""),
    )
    for sheet_id, cell_range in ALLOWED_SHEET_RANGES
}


# Readiness uses one bounded cell from a spreadsheet that is already in the
# server-side allowlist. Keep it separate from the public proxy allowlist so a
# health probe cannot broaden the public API surface.
READINESS_SHEET_ID = sorted(ALLOWED_SPREADSHEETS)[0]


READINESS_CELL_RANGE = "A1"


READINESS_SHEET_URL = UPSTREAM.format(
    sheet_id=READINESS_SHEET_ID,
    cell_range=urllib.parse.quote(READINESS_CELL_RANGE, safe=""),
)
