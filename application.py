import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd, portfolio, tot, transaction

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure database connection
engine = create_engine("postgres://drmddgon:nUUx80PXWwPZ_MH_aZWtBo9kQk4pcGbf@satao.db.elephantsql.com:5432/drmddgon")
db = scoped_session(sessionmaker(bind=engine))

# Make sure API key is set
# if not os.environ.get("API_KEY"):
#     raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query the DB for symbol, company name, num of share, for the given user
    uid = dict(cuid=session['user_id'])
    hs = db.execute("""WITH bought_shares AS (
                            SELECT cuid, ticker, SUM(num_shares) AS num_bought_shares
                            FROM transaction
                            WHERE cuid=:cuid AND trans_detail='by'
                            GROUP BY cuid, ticker
                            ORDER BY ticker),
                            
                            sold_shares AS (
                                SELECT cuid, ticker, SUM(num_shares) AS num_sold_shares
                                FROM transaction
                                WHERE cuid=:cuid AND trans_detail='sl'
                                GROUP BY cuid, ticker
                                ORDER BY ticker)
                                
                            SELECT t.ticker, t.company,
                                CASE
                                    WHEN b.num_bought_shares - s.num_sold_shares IS NULL THEN b.num_bought_shares
                                    ELSE b.num_bought_shares - s.num_sold_shares
                                END AS num_curr_shares
                            FROM transaction t
                            LEFT JOIN bought_shares b ON t.cuid=b.cuid AND t.ticker=b.ticker
                            LEFT JOIN sold_shares s ON t.cuid=s.cuid AND t.ticker=s.ticker
                            WHERE t.cuid=:cuid
                            GROUP BY t.ticker, t.company, num_curr_shares
                            ORDER BY t.ticker""", uid).fetchall()
    # the query returns list of tuples, convert them to dict objects using list comprehension
    # need to declare variables so the dict func can iterate over and create a list of dicts
    keys = ("ticker", "company", "num_shares")
    hold_share = [dict(zip(keys, values)) for values in hs]
    # Call the helper func on the list returned by the above function
    folio = portfolio(hold_share)
    # Call the helper func for the total value based on current share val
    total = float(tot())
    # Query for getting the current user cash bal and then change the dict in the list to float
    cash = db.execute("SELECT cash FROM users WHERE id=:cuid", uid).fetchall()
    avail_bal = float(format(cash[0][0], '.2f'))
    # Grand total is comprised of the avail bal, and the current holding share val
    grand_total = total + avail_bal

    return render_template("index.html", folio=folio, grand_total=usd(grand_total), avail_bal=usd(avail_bal))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via GET display the buy page
    if request.method == "GET":
        return render_template("buy.html")
    # Otherwise reached through POST (as by submitting a form via POST)
    else:
        # check if the ticker is valid and return apology if not
        if not request.form.get("symbol"):
            return apology("Missing Symbol", 400)

        # Ensure a positive integer for number of shares was submitted
        elif not request.form.get("shares"):
            return apology("Missing Shares", 400)

        else:
            # Pass the user inputted str to lookup helper func
            ticker = lookup(request.form.get("symbol"))
            # If  the response is empty, return apology
            if ticker is None:
                return apology("invalid symbol", 400)
            else:
                # if valid check how much cash the user has and how much the user selected shares cost
                # query user's available balance
                uid = dict(cuid=session['user_id'])
                cash = db.execute("SELECT cash FROM users WHERE id=:cuid", uid).fetchall()
                avail_bal = float(format(cash[0][0], '.2f'))
                # the return of price from the lookup above will be in dict, separate the price
                sel_share_val = ticker["price"]
                # get the number of shares from user input
                num_shares = int(request.form.get("shares"))
                # if user hasn't enough money to buy complete the transaction return apology
                if sel_share_val * num_shares > avail_bal:
                    return apology("You don't have enough balance!", 400)
                # Otherwise add the share to the user acc and deduct the money
                else:
                    # insert the purchase details in the db
                    cp = dict(company=ticker['name'])
                    tc = dict(ticker=ticker['symbol'])
                    pa = dict(price_atm=sel_share_val)
                    td = dict(trans_detail='by')
                    ns = dict(num_shares=num_shares)
                    buy_share = {**uid, **tc, **pa, **td, **ns, **cp}
                    db.execute("INSERT INTO transaction (cuid, ticker, price_atm, trans_detail, num_shares, company) VALUES (:cuid, :ticker, :price_atm, :trans_detail, :num_shares, :company)", buy_share)
                    # calculate the remaining bal for user after deducting his purchase
                    bal_updt = avail_bal - (sel_share_val * num_shares)
                    # update user acc with the new bal
                    bu = dict(cash=bal_updt)
                    update_bal = {**bu, **uid}
                    db.execute("UPDATE users SET cash = :cash WHERE id = :cuid", update_bal)
                    db.commit()
                    # display confirmation message and then return to portfolio
                    flash("Transaction(s) completed Successfully!")
                    # Redirect user to home page
                    return redirect("/")

@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    return jsonify("TODO")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query the DB for symbol, num of share, curr_price, transacted time for the given user
    uid = dict(cuid=session['user_id'])
    st = db.execute("SELECT ticker, CASE WHEN trans_detail = 'by' THEN num_shares::text ELSE '-' || num_shares::text END AS num_shares, price_atm, purchase_time FROM transaction WHERE cuid=:cuid ORDER BY purchase_time desc", uid).fetchall()
    keys = ("ticker", "num_shares", "price_atm", "purchase_time")
    share_trans = [dict(zip(keys, values)) for values in st]
    history = transaction(share_trans)
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        username = dict(username=request.form.get("username"))
        rows = db.execute("SELECT * FROM users WHERE username = :username", username).fetchall()
        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/password", methods=["GET", "POST"])
def password():
    """Lets the user change their password"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not (request.form.get("password") and request.form.get("confirmation")):
            return apology("must provide password", 403)

        # Query database for username
        username = dict(username=request.form.get("username"))
        rows = db.execute("SELECT * FROM users WHERE username = :username", username).fetchall()
        check_username = rows[0][1]

        # Check if username exists in the DB
        if len(check_username) == 0:
            flash("Sorry, username does not exist!")
            return render_template("password.html")

        else:
            # Hash the password and update the table
            hashed_pass = dict(hashed_pass=generate_password_hash(request.form.get("password")))
            user_creds = {**username, **hashed_pass}
            db.execute("UPDATE users SET hash=:hashed_pass", user_creds)
            db.commit()
            return redirect("/")

    else:
        return render_template("password.html")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via GET
    if request.method == "GET":
        return render_template("quote.html")

    # User reached route via POST
    else:
        # Pass the user inputted str to lookup helper func
        ticker = lookup(request.form.get("symbol"))
        # If  the response is empty, return apology
        if ticker is None:
            return apology("invalid symbol", 400)
        # Otherwise, return the dict from lookup to quoted
        else:
            return render_template("quoted.html", ticker=ticker)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not (request.form.get("password") and request.form.get("confirmation")):
            return apology("must provide password", 403)

        # Query database for username
        username = dict(username=request.form.get("username"))
        check_username = db.execute("SELECT * FROM users WHERE username = :username", username).fetchall()

        # Ensure username does not exist in the DB
        if len(check_username) > 0:
            flash("Sorry, username is already taken!")
            return render_template("register.html")

        else:
            # Add username, hash the password and add it to the DB
            hashed_pass = dict(hashed_pass=generate_password_hash(request.form.get("password")))
            create_creds = {**username, **hashed_pass}
            new_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashed_pass) RETURNING id", create_creds).fetchall()
            db.commit()
            flash("Registration Successfull!")
            session["user_id"] = new_user[0][0]
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Query the user inputted str to check if user has that in holding
    uid = dict(cuid=session['user_id'])
    hold_share = db.execute("""WITH bought_shares AS (
                            SELECT cuid, ticker, SUM(num_shares) AS num_bought_shares
                            FROM transaction
                            WHERE cuid=:cuid AND trans_detail='by'
                            GROUP BY cuid, ticker
                            ORDER BY ticker),
                            
                            sold_shares AS (
                                SELECT cuid, ticker, SUM(num_shares) AS num_sold_shares
                                FROM transaction
                                WHERE cuid=:cuid AND trans_detail='sl'
                                GROUP BY cuid, ticker
                                ORDER BY ticker)
                                
                            SELECT t.ticker,
                                CASE
                                    WHEN b.num_bought_shares - s.num_sold_shares IS NULL THEN b.num_bought_shares
                                    ELSE b.num_bought_shares - s.num_sold_shares
                                END AS num_curr_shares
                            FROM transaction t
                            LEFT JOIN bought_shares b ON t.cuid=b.cuid AND t.ticker=b.ticker
                            LEFT JOIN sold_shares s ON t.cuid=s.cuid AND t.ticker=s.ticker
                            WHERE t.cuid=:cuid
                            GROUP BY t.ticker, num_curr_shares
                            ORDER BY t.ticker""", uid).fetchall()
    
    # Convert output to a dict
    keys = ("ticker", "num_shares")
    own_share = [dict(zip(keys, values)) for values in hold_share]
    # SET comprehension to get the unique ticker names
    share_avail = {hold_share[i][0] for i in range(len(hold_share))}
    # User reached route via GET display the sell page
    if request.method == "GET":
        return render_template("sell.html", share_avail=share_avail)
    # Otherwise reached through POST (as by submitting a form via POST)
    else:
        # check if the ticker is valid and return apology if not
        if not request.form.get("symbol"):
            return apology("Missing Symbol", 400)

        # Ensure a positive integer for number of shares was submitted
        elif not request.form.get("shares"):
            return apology("Missing Shares", 400)
        # Ensure that the ticker name is available in the shares owned by the user
        elif request.form.get("symbol") not in share_avail:
            return apology("You don't own this share!", 400)

        else:
            for share in own_share:
                if share['ticker'] == request.form.get("symbol"):
                    if share['num_shares'] < int(request.form.get("shares")):
                        return apology("Too many Shares", 400)
                    else:
                        # since the return of price will be in dict, separate the price Pass the user inputted str to lookup helper func
                        ticker = lookup(request.form.get("symbol"))
                        sel_share_val = ticker['price']
                        # get the number of shares from user input
                        num_shares = int(request.form.get("shares"))
                        # insert the sold details in the db
                        cp = dict(company=ticker['name'])
                        tc = dict(ticker=request.form.get("symbol"))
                        pa = dict(price_atm=sel_share_val)
                        td = dict(trans_detail='sl')
                        ns = dict(num_shares=num_shares)
                        sell_share = {**uid, **tc, **pa, **td, **ns, **cp}
                        db.execute("INSERT INTO transaction (cuid, ticker, price_atm, trans_detail, num_shares, company) VALUES (:cuid, :ticker, :price_atm, :trans_detail, :num_shares, :company)", sell_share)
                        # Query for getting the current user cash bal and then change the dict in the list to float
                        cash_list = db.execute("SELECT cash FROM users WHERE id=:cuid", uid).fetchall()
                        avail_bal = float(format(cash_list[0][0], '.2f'))
                        # calculate the remaining bal for user after adding the value for the sold shares
                        bal_updt = avail_bal + (sel_share_val * num_shares)
                        # update user acc with the new bal
                        bu = dict(cash=bal_updt)
                        update_bal = {**bu, **uid}
                        db.execute("UPDATE users SET cash = :cash WHERE id = :cuid", update_bal)
                        db.commit()
                        # display confirmation message and then return to portfolio
                        flash("Transaction(s) completed Successfully!")
                        # Redirect user to home page
                        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
