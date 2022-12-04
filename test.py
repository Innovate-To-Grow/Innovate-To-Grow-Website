import asyncio
import yagmail
import time
from gspread.cell import Cell
from project import app, wks
from flask import render_template, url_for
from project.utils.email import send_email
from project.utils.index_helper import wks_indices, arr_indices
from project.utils.token import generate_token

wks_idx = wks_indices()
email = "alvin.toto258@gmail.com"

async def query_prim_col():
    return wks.find(email, in_column=wks_idx["Primary Email"])

async def query_sec_col():
    return wks.find(email, in_column=wks_idx["Secondary Email"])

async def main():
    return await asyncio.gather(query_prim_col(), query_sec_col())

if __name__ == "__main__":
    l = asyncio.run(main())
    # make it so User variable is equal to value in l if it's not None
    User = l[0] if l[0] is not None else l[1] if l[1] is not None else None

    print(User)