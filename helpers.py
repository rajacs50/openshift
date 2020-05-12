import os
import requests
import urllib.parse

from flask import redirect, render_template, request, session
from functools import wraps
import settings


def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""

    # Contact API
    try:
        api_key = os.environ.get("API_KEY")
        response = requests.get(f"https://cloud-sse.iexapis.com/stable/stock/{urllib.parse.quote_plus(symbol)}/quote?token={api_key}")
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        quote = response.json()
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"


def portfolio(hold_share):
    """
    Expects a list of dict as the input, iterates through each dict elem from the list
    outputs another list with the symbol, num of shares, curr price (using lookup helper func)
    total holding share val
    """
    share_detail = []
    global total
    total = 0
    for share in hold_share:
        stock = {}
        stock['ticker'] = share['ticker']
        stock['num_shares'] = share['num_shares']
        stock['curr_price'] = lookup(stock['ticker'])
        stock['total_holding'] = stock['num_shares'] * stock['curr_price']['price']
        total += stock['total_holding']
        share_detail.append(stock)
    return share_detail


def tot():
    """
    Just to return the total from the portfolio func
    """
    return total


def transaction(share_trans):
    """
    Expects a list of dict as the input, iterates through each dict elem from the list
    outputs another list with the symbol, num of shares, price at the time of purchase
    transacted time.
    """
    share_detail = []
    for share in share_trans:
        stock = {}
        stock['ticker'] = share['ticker']
        stock['num_shares'] = share['num_shares']
        stock['price_atm'] = share['price_atm']
        stock['purchase_time'] = share['purchase_time']
        share_detail.append(stock)
    return share_detail

# def transaction(*args):
#     """
#     Expects a list of dict as the input, iterates through each dict elem from the list
#     outputs another list with the symbol, num of shares, price at the time of purchase
#     transacted time.
#     """
#     share_detail = []
#     for share in share_trans:
#         stock = {}
#         stock['ticker'] = share['ticker']
#         stock['num_shares'] = share['num_shares']
#         stock['price_atm'] = share['price_atm']
#         stock['purchase_time'] = share['purchase_time']
#         share_detail.append(stock)
#     return share_detail