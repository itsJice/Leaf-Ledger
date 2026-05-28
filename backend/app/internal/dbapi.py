import databutton as db
import httpx


def get_dbapi_client() -> httpx.Client:
    return db.internal.dbapiclient.get_dbapi_client()
